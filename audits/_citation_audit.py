"""
Citation-integrity audit for ContentPrinter Posts/<slug>/en/draft.txt REFERENCES blocks.

Task #21 (researcher, 2026-04-12). This script is the reference implementation
for the verification logic CentralStrengthKB will import as its F-0 gate
(CentralStrengthKB ROADMAP v2, Objective F-0). Keep it importable and side-effect-free
except for the __main__ block at the bottom, which writes the two audit outputs.

Severity ladder (most severe first):
  NO_SUCH_PAPER           - PubMed search for (author, year, journal) returned nothing; no DOI
  DOI_WRONG               - DOI resolves but author + title mismatch with the draft citation
  DOI_UNRESOLVABLE        - Crossref HTTP 404 on the DOI AND doi.org HEAD 404; DOI does not exist anywhere
  NO_VERIFIABLE_SOURCE    - no DOI, no PMID, PubMed search ambiguous (too many hits, none dominant)
  DOI_MISATTRIBUTED       - DOI resolves to a paper whose title matches the draft (>=0.8) but
                            first-author differs. Draft text is probably right, DOI field is wrong.
  AUTHOR_WRONG            - DOI resolves, title mostly matches (0.25..0.8) but author differs
  YEAR_WRONG              - author + title match, year off by >1
  TITLE_MISMATCH          - author + year match, title overlap < 0.25
  JOURNAL_MISMATCH        - everything else OK, journal family doesn't match
  OK                      - everything matches
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

CONTACT_EMAIL = "contentprinter@centralstrengthgyms.com"
UA = f"ContentPrinter/0.1 (mailto:{CONTACT_EMAIL})"

STOPWORDS = {
    "the","and","for","with","from","into","over","under","between","among","more","less","than","that",
    "this","these","those","their","there","which","where","when","what","have","has","been","were",
    "are","was","is","a","an","of","in","on","to","by","as","at","be","or","vs","versus","systematic",
    "review","meta-analysis","meta","analysis","effect","effects","influence","impact","results","study",
    "studies","trial","trials","randomized","randomised","controlled","double-blind","placebo","position",
    "stand","narrative","gains","recommendations","recommendation","based","evidence",
}

JOURNAL_ABBR = {
    "j":"journal","jour":"journal","int":"international","intl":"international","soc":"society",
    "sport":"sports","sports":"sports","nutr":"nutrition","med":"medicine","sci":"science",
    "exerc":"exercise","cond":"conditioning","res":"research","physiol":"physiology",
    "appl":"applied","br":"british","am":"american","eur":"european","obes":"obesity",
    "clin":"clinical","phys":"physical","ther":"therapy","rehabil":"rehabilitation",
    "strength":"strength","cardiovasc":"cardiovascular","nutrit":"nutrition",
    "biomech":"biomechanics","endocrinol":"endocrinology","metab":"metabolism",
    "perform":"performance","transl":"translational","myol":"myology","bmj":"british medical",
    "jama":"american medical","age":"ageing","agei":"ageing","nephr":"nephrology",
    "eat":"eating","behav":"behaviors","pediatr":"pediatric","orthop":"orthopaedics",
    "kinet":"kinetics","hum":"human","behavior":"behaviors","orthopaedic":"orthopaedics",
    "orthopedics":"orthopaedics","orthopedic":"orthopaedics",
}

# Sources that aren't expected to be in Crossref / PubMed (books, institutional reports,
# blog posts, YouTube videos). Matching these triggers NOT_PUBMED_INDEXED instead of
# NO_VERIFIABLE_SOURCE so editors can see the non-peer-reviewed references separately.
NON_ACADEMIC_PATTERNS = [
    r"\bYouTube\b",
    r"\bACE Fitness\b",
    r"\bGatorade\b",
    r"\bNSCA\b.*(Essentials|Chapter)",
    r"Essentials of Strength Training",
    r"Low Back Disorders.*Edition",
    r"\bNippard\b",
    r"\b\d(?:st|nd|rd|th)\s+Edition\b",
]

TITLE_OVERLAP_PASS = 0.25
TITLE_OVERLAP_STRICT = 0.80
YEAR_TOLERANCE = 1


def _tokens(s):
    if not s:
        return set()
    s = s.lower().replace("-", " ").replace("\u2013", " ").replace("\u2010", " ")
    return {w for w in re.findall(r"[a-z0-9]{4,}", s) if w not in STOPWORDS}


def title_overlap(draft_title, fetched_title):
    a, b = _tokens(draft_title), _tokens(fetched_title)
    if not b:
        return 0.0
    return len(a & b) / len(b)


def _jtokens(s):
    if not s:
        return set()
    out = set()
    for w in re.findall(r"[a-z]+", s.lower()):
        out.add(JOURNAL_ABBR.get(w, w))
    return out - {"of", "and", "the", "a", "an", "in", "for", "to"}


def journal_family_match(draft_journal, fetched_journal):
    a, b = _jtokens(draft_journal), _jtokens(fetched_journal)
    if not a or not b:
        return True
    shared = a & b
    return len(shared) >= 2 or (len(shared) / max(len(a), len(b)) >= 0.5)


def _strip_diacritics(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def surname(s):
    if not s:
        return None
    s = _strip_diacritics(s)
    parts = s.strip().split()
    if not parts:
        return None
    return parts[0].lower().replace("-", "")


def is_non_academic(ref_raw):
    for p in NON_ACADEMIC_PATTERNS:
        if re.search(p, ref_raw, re.IGNORECASE):
            return True
    return False


def parse_refs_block(draft_text):
    m = re.search(r"REFERENCES:\s*\n(.+?)(?:\n-{5,}|\n={5,}|\Z)", draft_text, re.DOTALL | re.IGNORECASE)
    if not m:
        return []
    block = m.group(1)
    out = []
    for line in block.split("\n"):
        mm = re.match(r"\s*(\d+)\.\s*(.+?)\s*$", line)
        if mm:
            out.append((int(mm.group(1)), mm.group(2)))
    return out


def extract_fields(ref_text):
    author = None
    year = None
    title = None
    ym = re.search(r"\((\d{4})\)\s*\.", ref_text)
    if ym:
        year = int(ym.group(1))
        before = ref_text[: ym.start()].strip()
        before = re.sub(r"\s+et\s+al\.?\s*$", "", before, flags=re.I)
        before = re.sub(
            r"\s*&\s+[A-Z][\w\-']*(?:\s+[A-Z][\w\-']*)*(?:\s+[A-Z]{1,3})?\s*$",
            "",
            before,
        )
        before = before.rstrip(",. ")
        parts = before.split()
        if parts and re.match(r"^[A-Z]{1,3}$", parts[-1]):
            author = " ".join(parts[:-1])
        else:
            author = before
        after = ref_text[ym.end():].lstrip(" .")
        tparts = re.split(r"\.\s+(?=[A-Z])", after, maxsplit=1)
        if tparts:
            title = tparts[0].strip().rstrip(".")
    else:
        tparts = re.split(r"\.\s+(?=[A-Z])", ref_text, maxsplit=1)
        if tparts:
            title = tparts[0].strip().rstrip(".")

    doi = None
    dm = re.search(
        r"(?:doi\s*:\s*|doi\.org/)(10\.\S+?)(?:\s|$|PMID|PMCID|\n)",
        ref_text,
        re.IGNORECASE,
    )
    if dm:
        doi = dm.group(1).rstrip(".,;)")

    pmid = None
    pm = re.search(r"PMID[:\s]+(\d{5,9})", ref_text)
    if pm:
        pmid = pm.group(1)

    return {"first_author": author, "year": year, "doi": doi, "pmid": pmid, "title": title}


def draft_journal_of(ref_raw, title):
    if not title:
        return None
    i = ref_raw.find(title)
    if i < 0:
        return None
    tail = ref_raw[i + len(title):].lstrip(" .")
    m = re.match(r"([^,\.]+?)(?:,|\s+\d)", tail)
    return m.group(1).strip() if m else None


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _head(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return None


def crossref_by_doi(doi):
    u = f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='/')}?mailto={CONTACT_EMAIL}"
    j = json.loads(_get(u))
    m = j.get("message", {})
    t = (m.get("title") or [None])[0]
    authors = m.get("author") or []
    first = authors[0].get("family") if authors else None
    dp = (m.get("issued", {}).get("date-parts") or [[None]])[0]
    year = dp[0] if dp else None
    journal = (m.get("container-title") or [None])[0]
    return {"title": t, "first_author": first, "year": year, "journal": journal}


def doi_exists(doi):
    """Check if doi.org recognizes the DOI (beyond Crossref's database)."""
    u = f"https://doi.org/{urllib.parse.quote(doi, safe='/')}"
    status = _head(u)
    return status is not None and 200 <= status < 400


def pubmed_search_triplet(author, year, title_keywords):
    """Phase 2: for no-DOI refs, search PubMed with author[AU] + journal + year and the main title keywords."""
    if not author or not year:
        return None
    tw = " ".join(sorted(title_keywords)[:6])
    q = f"{author}[AU] AND {year}[dp]"
    if tw:
        q += f" AND ({tw})"
    u = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={urllib.parse.quote(q)}&retmode=json&retmax=5"
    try:
        j = json.loads(_get(u))
    except Exception:
        return None
    ids = j.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return None
    # Fetch esummary for the first hit, verify it's real
    u = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={ids[0]}&retmode=json"
    try:
        s = json.loads(_get(u)).get("result", {}).get(ids[0], {})
    except Exception:
        return None
    authors = s.get("authors", []) or []
    first = authors[0].get("name", "").split(" ")[0] if authors else None
    ym = re.match(r"(\d{4})", s.get("pubdate", ""))
    return {
        "pmid": ids[0],
        "title": s.get("title"),
        "first_author": first,
        "year": int(ym.group(1)) if ym else None,
        "journal": s.get("fulljournalname") or s.get("source"),
    }


def classify(draft, fetched, draft_journal):
    """Return severity label based on draft vs fetched record."""
    dsur = surname(draft["first_author"])
    fsur = surname(fetched["first_author"]) if fetched else None
    am = (dsur == fsur) if (dsur and fsur) else None
    ym = (abs(draft["year"] - fetched["year"]) <= YEAR_TOLERANCE) if (draft.get("year") and fetched and fetched.get("year")) else None
    ov = title_overlap(draft["title"], fetched["title"]) if fetched else 0.0
    jm = journal_family_match(draft_journal, fetched["journal"]) if fetched else True

    if am is False and ov < TITLE_OVERLAP_PASS:
        return "DOI_WRONG", {"author_match": am, "year_match": ym, "title_overlap": round(ov, 3), "journal_match": jm}
    if am is False and ov >= TITLE_OVERLAP_STRICT:
        return "DOI_MISATTRIBUTED", {"author_match": am, "year_match": ym, "title_overlap": round(ov, 3), "journal_match": jm}
    if am is False:
        return "AUTHOR_WRONG", {"author_match": am, "year_match": ym, "title_overlap": round(ov, 3), "journal_match": jm}
    if ym is False and ov < TITLE_OVERLAP_PASS:
        return "DOI_WRONG", {"author_match": am, "year_match": ym, "title_overlap": round(ov, 3), "journal_match": jm}
    if ym is False:
        return "YEAR_WRONG", {"author_match": am, "year_match": ym, "title_overlap": round(ov, 3), "journal_match": jm}
    if ov < TITLE_OVERLAP_PASS:
        return "TITLE_MISMATCH", {"author_match": am, "year_match": ym, "title_overlap": round(ov, 3), "journal_match": jm}
    if not jm:
        return "JOURNAL_MISMATCH", {"author_match": am, "year_match": ym, "title_overlap": round(ov, 3), "journal_match": jm}
    return "OK", {"author_match": am, "year_match": ym, "title_overlap": round(ov, 3), "journal_match": jm}


def audit_draft(draft_text, slug):
    """Verify every REFERENCES entry in a single draft.txt body. Returns a list of row dicts."""
    rows = []
    for idx, raw in parse_refs_block(draft_text):
        fields = extract_fields(raw)
        dj = draft_journal_of(raw, fields["title"])
        row = {
            "slug": slug,
            "ref_idx": idx,
            "raw": raw,
            "draft": {
                "first_author": fields["first_author"],
                "year": fields["year"],
                "title": fields["title"],
                "journal": dj,
                "doi": fields["doi"],
                "pmid": fields["pmid"],
            },
            "fetched": None,
            "verify": {},
            "severity": "UNCHECKED",
            "notes": None,
        }

        if fields["doi"]:
            try:
                fetched = crossref_by_doi(fields["doi"])
                row["fetched"] = fetched
                sev, verify = classify(row["draft"], fetched, dj)
                row["verify"] = verify
                row["severity"] = sev
            except Exception as e:
                exists = doi_exists(fields["doi"])
                row["fetch_error"] = str(e)[:140]
                if exists:
                    row["severity"] = "DOI_UNRESOLVABLE"
                    row["notes"] = "Crossref lookup failed but doi.org accepts the DOI (redirect 200-range). Paper may be genuine but not yet indexed by Crossref."
                else:
                    row["severity"] = "DOI_FABRICATED"
                    row["notes"] = "Neither Crossref nor doi.org can resolve this DOI. The DOI string appears to be fabricated."
        elif fields["pmid"]:
            try:
                u = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={fields['pmid']}&retmode=json"
                r = (json.loads(_get(u)).get("result", {}) or {}).get(fields["pmid"], {}) or {}
                authors = r.get("authors", []) or []
                first = authors[0].get("name", "").split(" ")[0] if authors else None
                ymatch = re.match(r"(\d{4})", r.get("pubdate", ""))
                fetched = {
                    "title": r.get("title"),
                    "first_author": first,
                    "year": int(ymatch.group(1)) if ymatch else None,
                    "journal": r.get("fulljournalname") or r.get("source"),
                }
                if not fetched["title"]:
                    row["severity"] = "PMID_NOT_FOUND"
                    row["notes"] = "PubMed returned empty record for this PMID."
                else:
                    row["fetched"] = fetched
                    sev, verify = classify(row["draft"], fetched, dj)
                    row["verify"] = verify
                    row["severity"] = sev
            except Exception as e:
                row["severity"] = "PMID_FETCH_ERROR"
                row["fetch_error"] = str(e)[:140]
        elif is_non_academic(raw):
            row["severity"] = "NOT_PUBMED_INDEXED"
            row["notes"] = "Textbook / institutional report / YouTube video / non-peer-reviewed source. Not verifiable via Crossref/PubMed. Editor should confirm the source exists and the quoted figures are accurate by hand."
        else:
            # No DOI and no PMID: try PubMed author-year-title search
            kw = _tokens(fields["title"])
            hit = pubmed_search_triplet(fields["first_author"], fields["year"], kw)
            if hit:
                row["fetched"] = hit
                sev, verify = classify(row["draft"], hit, dj)
                # Downgrade severity threshold for no-DOI refs - a matching hit is enough for OK
                row["verify"] = verify
                row["severity"] = sev
                row["notes"] = f"Matched via PubMed author+year+title search (no DOI in draft). PMID={hit['pmid']}"
            else:
                row["severity"] = "NO_VERIFIABLE_SOURCE"
                row["notes"] = "No DOI, no PMID in the draft, and PubMed search on (first_author, year, title keywords) returned no hits."

        rows.append(row)
        time.sleep(0.15)
    return rows


def run_audit(posts_root):
    slugs = sorted(
        d for d in os.listdir(posts_root)
        if os.path.isdir(os.path.join(posts_root, d))
        and os.path.exists(os.path.join(posts_root, d, "en", "draft.txt"))
    )
    all_rows = []
    for i, slug in enumerate(slugs, 1):
        print(f"[{i}/{len(slugs)}] {slug}", file=sys.stderr)
        text = open(os.path.join(posts_root, slug, "en", "draft.txt")).read()
        all_rows.extend(audit_draft(text, slug))
    return all_rows


if __name__ == "__main__":
    ROOT = "/opt/home/buckcenter.org/hcheng/ContentPrinter/Posts"
    rows = run_audit(ROOT)
    out_json = os.path.join(os.path.dirname(os.path.abspath(__file__)), "citation_integrity_2026-04-12.json")
    with open(out_json, "w") as f:
        json.dump({"rows": rows, "generated_at": "2026-04-12", "generator": "audits/_citation_audit.py"}, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {out_json}", file=sys.stderr)
    # Severity summary
    by = {}
    for r in rows:
        by[r["severity"]] = by.get(r["severity"], 0) + 1
    print("Severity counts:", file=sys.stderr)
    for k, v in sorted(by.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}", file=sys.stderr)
