"""
PubMed Scraper for Central Strength Gym
Searches PubMed for exercise science, nutrition, and sports medicine studies
using the NCBI E-utilities (Entrez) API.
"""

import json
import time
import hashlib
from datetime import datetime
from pathlib import Path

from http_utils import create_session, get as http_get

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
POSTS_DIR = PROJECT_ROOT / "work"  # internal scratch; final output in Posts/ via output_layout.finalize

ENTREZ_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
# NCBI asks for an email with E-utilities requests; no API key needed for <3 req/sec
ENTREZ_EMAIL = "contentprinter@centralstrengthgyms.com"

_session = create_session()


def load_config():
    with open(CONFIG_DIR / "config.json") as f:
        config = json.load(f)
    with open(CONFIG_DIR / "sources.json") as f:
        sources = json.load(f)
    return config, sources


def content_hash(text):
    """Generate hash to avoid duplicate content."""
    return hashlib.md5(text.encode()).hexdigest()[:12]


def search_pubmed(query, max_results=20, min_date=None):
    """Search PubMed and return a list of PMIDs."""
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
        "sort": "relevance",
        "email": ENTREZ_EMAIL,
    }
    if min_date:
        params["mindate"] = min_date
        params["datetype"] = "pdat"

    try:
        resp = http_get(_session, f"{ENTREZ_BASE}/esearch.fcgi", params=params, timeout=15)
        data = resp.json()
        return data.get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        print(f"  [ERROR] PubMed search failed for '{query}': {e}")
        return []


def fetch_article_details(pmids):
    """Fetch detailed metadata for a list of PMIDs using efetch."""
    if not pmids:
        return []

    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        "email": ENTREZ_EMAIL,
    }

    try:
        resp = http_get(_session, f"{ENTREZ_BASE}/efetch.fcgi", params=params, timeout=30)
        return parse_pubmed_xml(resp.text)
    except Exception as e:
        print(f"  [ERROR] PubMed fetch failed: {e}")
        return []


def parse_pubmed_xml(xml_text):
    """Parse PubMed XML response into structured article dicts."""
    import xml.etree.ElementTree as ET

    articles = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"  [ERROR] XML parse error: {e}")
        return []

    for article_elem in root.findall(".//PubmedArticle"):
        try:
            medline = article_elem.find("MedlineCitation")
            if medline is None:
                continue

            pmid_elem = medline.find("PMID")
            pmid = pmid_elem.text if pmid_elem is not None else ""

            art = medline.find("Article")
            if art is None:
                continue

            # Title
            title_elem = art.find("ArticleTitle")
            title = title_elem.text if title_elem is not None else ""
            if not title:
                continue

            # Authors
            authors = []
            author_list = art.find("AuthorList")
            if author_list is not None:
                for author in author_list.findall("Author"):
                    last = author.find("LastName")
                    fore = author.find("ForeName")
                    if last is not None and last.text:
                        name = last.text
                        if fore is not None and fore.text:
                            name = f"{fore.text} {last.text}"
                        authors.append(name)

            # Journal
            journal_elem = art.find("Journal/Title")
            journal = journal_elem.text if journal_elem is not None else ""

            # Year
            year = ""
            pub_date = art.find("Journal/JournalIssue/PubDate")
            if pub_date is not None:
                year_elem = pub_date.find("Year")
                if year_elem is not None:
                    year = year_elem.text
                else:
                    medline_date = pub_date.find("MedlineDate")
                    if medline_date is not None and medline_date.text:
                        year = medline_date.text[:4]

            # DOI
            doi = ""
            for id_elem in art.findall("ELocationID"):
                if id_elem.get("EIdType") == "doi":
                    doi = id_elem.text or ""
                    break
            if not doi:
                article_ids = article_elem.find("PubmedData/ArticleIdList")
                if article_ids is not None:
                    for aid in article_ids.findall("ArticleId"):
                        if aid.get("IdType") == "doi":
                            doi = aid.text or ""
                            break

            # Abstract
            abstract_parts = []
            abstract_elem = art.find("Abstract")
            if abstract_elem is not None:
                for abs_text in abstract_elem.findall("AbstractText"):
                    label = abs_text.get("Label", "")
                    text = abs_text.text or ""
                    # Also gather any tail text from sub-elements
                    full_text = "".join(abs_text.itertext())
                    if label:
                        abstract_parts.append(f"{label}: {full_text}")
                    else:
                        abstract_parts.append(full_text)
            abstract = "\n".join(abstract_parts)

            # MeSH terms
            mesh_terms = []
            mesh_list = medline.find("MeshHeadingList")
            if mesh_list is not None:
                for mesh in mesh_list.findall("MeshHeading/DescriptorName"):
                    if mesh.text:
                        mesh_terms.append(mesh.text)

            articles.append({
                "pmid": pmid,
                "title": title,
                "authors": authors,
                "journal": journal,
                "year": year,
                "doi": doi,
                "abstract": abstract,
                "mesh_terms": mesh_terms,
            })

        except Exception as e:
            print(f"  [WARN] Failed to parse article: {e}")
            continue

    return articles


def scrape_pubmed():
    """Main function -- search PubMed for relevant exercise science studies."""
    config, sources = load_config()
    settings = config["scrape_settings"]

    pubmed_config = sources.get("pubmed_searches", [])
    if not pubmed_config:
        print("[WARN] No pubmed_searches defined in sources.json. Skipping PubMed.")
        return []

    raw_dir = POSTS_DIR / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # Load seen hashes
    seen_file = POSTS_DIR / ".seen_pubmed_hashes.json"
    if seen_file.exists():
        with open(seen_file) as f:
            seen_hashes = set(json.load(f))
    else:
        seen_hashes = set()

    all_articles = []

    print(f"\n{'='*60}")
    print(f"  PUBMED SCRAPER -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    for search in pubmed_config:
        query = search["query"]
        topic = search.get("topic", "training")
        max_results = search.get("max_results", 10)

        print(f"[SEARCH] {query}")
        print(f"  Topic: {topic}, Max results: {max_results}")

        # Rate limit: 1 request per second for NCBI
        time.sleep(1)
        pmids = search_pubmed(query, max_results=max_results)
        print(f"  Found {len(pmids)} PMIDs")

        if not pmids:
            continue

        # Filter out already-seen PMIDs before fetching details
        new_pmids = [p for p in pmids if content_hash(f"pubmed:{p}") not in seen_hashes]
        if not new_pmids:
            print("  [SKIP] All articles already seen")
            continue

        print(f"  Fetching details for {len(new_pmids)} new articles...")
        time.sleep(1)  # Rate limit
        articles = fetch_article_details(new_pmids)
        print(f"  Retrieved {len(articles)} articles")

        for article in articles:
            h = content_hash(f"pubmed:{article['pmid']}")
            if h in seen_hashes:
                continue

            # Build structured output compatible with the pipeline
            entry = {
                "title": article["title"],
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{article['pmid']}/",
                "source": f"PubMed ({article['journal']})" if article["journal"] else "PubMed",
                "source_type": "pubmed",
                "topic": topic,
                "summary": article["abstract"][:500] if article["abstract"] else "",
                "full_text": article["abstract"][:20000],
                "structured_content": {
                    "pmid": article["pmid"],
                    "authors": article["authors"],
                    "journal": article["journal"],
                    "year": article["year"],
                    "doi": article["doi"],
                    "mesh_terms": article["mesh_terms"],
                },
                "scraped_at": datetime.now().isoformat(),
                "hash": h,
            }

            all_articles.append(entry)
            seen_hashes.add(h)
            print(f"  [OK] {article['title'][:70]}...")

        print()

    # Save results
    if all_articles:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        outfile = raw_dir / f"pubmed_{timestamp}.json"
        with open(outfile, "w") as f:
            json.dump(all_articles, f, indent=2)
        print(f"[SAVED] {len(all_articles)} PubMed articles -> {outfile}")

        with open(seen_file, "w") as f:
            json.dump(list(seen_hashes), f)
    else:
        print("[INFO] No new PubMed articles found.")

    print(f"\n{'='*60}\n")
    return all_articles


if __name__ == "__main__":
    articles = scrape_pubmed()
    print(f"Total PubMed articles scraped: {len(articles)}")
