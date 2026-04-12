# Citation Integrity Audit — ContentPrinter

**Date:** 2026-04-12  
**Auditor:** researcher (Task #21)  
**Scope:** all 31 migrated posts in `Posts/<slug>/en/draft.txt`, REFERENCES block parsed per-line.  
**Method:** see `audits/_citation_audit.py` — Crossref DOI lookup + doi.org fallback + PubMed fallback for no-DOI refs, then strict verification (first-author surname + year ±1 + ≥25% title word overlap + journal-family match).  
**Total refs audited:** 164  

## Executive summary

| Severity | Count | Meaning |
|---|---:|---|
| `DOI_FABRICATED` | 7 | DOI does not exist — doi.org returns 404. The DOI string appears to be a drafter hallucination. |
| `DOI_WRONG` | 13 | DOI resolves to a completely unrelated paper (different author and title). Either the DOI was copied from a random paper or fabricated to look plausible. |
| `DOI_MISATTRIBUTED` | 9 | DOI resolves to a paper whose title matches the draft (>=80% word overlap) but the first author differs. Usually means the drafter invented a fake author name and attached it to a real paper's title + DOI. |
| `NO_VERIFIABLE_SOURCE` | 21 | No DOI, no PMID in the draft, and PubMed author+year+title search returned no hits. Cannot verify the paper exists. HIGH FABRICATION RISK. |
| `YEAR_WRONG` | 1 | Author and title match but publication year is off by >1 from the draft. |
| `JOURNAL_MISMATCH` | 5 | Everything else matches but the cited journal differs from the actual venue. Minor error — usually the drafter recorded the wrong journal name for a real paper. |
| `NOT_PUBMED_INDEXED` | 6 | Textbook / institutional report / YouTube video / non-peer-reviewed source. Not verifiable via Crossref/PubMed. Editor must confirm by hand. |
| `OK` | 102 | Author, year, title (≥25% word overlap), and journal family all verified against Crossref or PubMed. |

**Most affected posts** (posts with the highest absolute count of non-OK citations):

| Post slug | non-OK / total | Breakdown |
|---|:---:|---|
| `nutrition_omega3_recovery` | 5/6 | DOI_MISATTRIBUTED=1, DOI_WRONG=1, NOT_PUBMED_INDEXED=1, NO_VERIFIABLE_SOURCE=2 |
| `nutrition_sleep_recovery` | 4/6 | DOI_FABRICATED=1, DOI_MISATTRIBUTED=2, DOI_WRONG=1 |
| `yt_training_exercises` | 4/5 | DOI_WRONG=1, JOURNAL_MISMATCH=1, NOT_PUBMED_INDEXED=1, NO_VERIFIABLE_SOURCE=1 |
| `yt_training_upper_body` | 4/5 | DOI_WRONG=1, NOT_PUBMED_INDEXED=1, NO_VERIFIABLE_SOURCE=2 |
| `nutrition_caffeine_strength` | 3/5 | DOI_MISATTRIBUTED=2, DOI_WRONG=1 |
| `nutrition_vegan_creatine` | 3/4 | DOI_MISATTRIBUTED=2, NOT_PUBMED_INDEXED=1 |
| `supplements_magnesium` | 3/7 | DOI_FABRICATED=1, DOI_WRONG=1, YEAR_WRONG=1 |
| `yt_powerlifting_program` | 3/5 | NO_VERIFIABLE_SOURCE=3 |
| `yt_training_past_failure` | 3/5 | DOI_WRONG=1, NO_VERIFIABLE_SOURCE=2 |
| `yt_volume` | 3/5 | DOI_FABRICATED=1, JOURNAL_MISMATCH=1, NO_VERIFIABLE_SOURCE=1 |
| `cardio_zone2` | 2/6 | DOI_WRONG=2 |
| `nutrition_clean_eating_myth` | 2/5 | DOI_WRONG=1, JOURNAL_MISMATCH=1 |
| `nutrition_whey_vs_collagen` | 2/5 | DOI_FABRICATED=1, NO_VERIFIABLE_SOURCE=1 |
| `rehab_low_back_pain` | 2/7 | DOI_WRONG=1, NOT_PUBMED_INDEXED=1 |
| `training_beginner_program` | 2/5 | DOI_WRONG=1, NOT_PUBMED_INDEXED=1 |
| `training_squat_mistakes` | 2/5 | NO_VERIFIABLE_SOURCE=2 |
| `yt_bench_shoulder_injury` | 2/5 | NO_VERIFIABLE_SOURCE=2 |
| `yt_deadlift_accessories` | 2/5 | NO_VERIFIABLE_SOURCE=2 |
| `yt_training_volume_cut` | 2/5 | DOI_FABRICATED=1, JOURNAL_MISMATCH=1 |
| `cardio_concurrent_training` | 1/6 | DOI_WRONG=1 |
| `nutrition_carb_timing` | 1/5 | DOI_MISATTRIBUTED=1 |
| `nutrition_vitamin_d` | 1/6 | DOI_MISATTRIBUTED=1 |
| `rehab_shoulder_prehab` | 1/7 | DOI_FABRICATED=1 |
| `training_bench_mistakes` | 1/5 | NO_VERIFIABLE_SOURCE=1 |
| `training_masters_lifters` | 1/5 | JOURNAL_MISMATCH=1 |
| `training_texas_method` | 1/5 | DOI_FABRICATED=1 |
| `training_warmups` | 1/4 | NO_VERIFIABLE_SOURCE=1 |
| `yt_protein_excess` | 1/6 | NO_VERIFIABLE_SOURCE=1 |

## Publication readiness

- **4 / 31 posts** are citation-clean and safe to publish (only `OK`, `JOURNAL_MISMATCH`, `YEAR_WRONG`, or `NOT_PUBMED_INDEXED` entries):

  - `nutrition_fat_myth`
  - `supplements_beta_alanine`
  - `training_hafthor_diet`
  - `training_masters_lifters`

- **27 / 31 posts** have at least one publication-blocking citation issue (any `DOI_FABRICATED`, `DOI_WRONG`, `DOI_MISATTRIBUTED`, `NO_VERIFIABLE_SOURCE`, `PMID_NOT_FOUND`, `AUTHOR_WRONG`, or `TITLE_MISMATCH`):

  - `cardio_concurrent_training`
  - `cardio_zone2`
  - `nutrition_caffeine_strength`
  - `nutrition_carb_timing`
  - `nutrition_clean_eating_myth`
  - `nutrition_omega3_recovery`
  - `nutrition_sleep_recovery`
  - `nutrition_vegan_creatine`
  - `nutrition_vitamin_d`
  - `nutrition_whey_vs_collagen`
  - `rehab_low_back_pain`
  - `rehab_shoulder_prehab`
  - `supplements_magnesium`
  - `training_beginner_program`
  - `training_bench_mistakes`
  - `training_squat_mistakes`
  - `training_texas_method`
  - `training_warmups`
  - `yt_bench_shoulder_injury`
  - `yt_deadlift_accessories`
  - `yt_powerlifting_program`
  - `yt_protein_excess`
  - `yt_training_exercises`
  - `yt_training_past_failure`
  - `yt_training_upper_body`
  - `yt_training_volume_cut`
  - `yt_volume`

## `DOI_FABRICATED` — 7 entries

_DOI does not exist — doi.org returns 404. The DOI string appears to be a drafter hallucination._

### `nutrition_sleep_recovery` ref 4

**Draft text:**  
`Vitale KC et al. (2019). Sleep hygiene for optimizing recovery in athletes. Int J Sports Physiol Perform, 14(2):144-148. doi:10.1123/ijspp.2019-0032`

**Fetch error:** `HTTP Error 404: Not Found`
**Notes:** Neither Crossref nor doi.org can resolve this DOI. The DOI string appears to be fabricated.

### `nutrition_whey_vs_collagen` ref 4

**Draft text:**  
`Bagheri R et al. (2024). Even vs skewed protein distribution and muscle protein synthesis. Front Nutr. doi:10.3389/fnut.2024.1567438`

**Fetch error:** `HTTP Error 404: Not Found`
**Notes:** Neither Crossref nor doi.org can resolve this DOI. The DOI string appears to be fabricated.

### `rehab_shoulder_prehab` ref 4

**Draft text:**  
`Reinold MM et al. (2009). Electromyographic analysis of the rotator cuff and deltoid musculature during common shoulder external rotation exercises. J Orthop Sports Phys Ther, 39(3):105-117. doi:10.2519/jospt.2009.2848`

**Fetch error:** `HTTP Error 404: Not Found`
**Notes:** Neither Crossref nor doi.org can resolve this DOI. The DOI string appears to be fabricated.

### `supplements_magnesium` ref 1

**Draft text:**  
`Wang R et al. (2017). Effects of magnesium supplementation on muscle performance: a meta-analysis. Biol Trace Elem Res, 180(2):261-268. doi:10.1007/s12011-017-1084-0`

**Fetch error:** `HTTP Error 404: Not Found`
**Notes:** Neither Crossref nor doi.org can resolve this DOI. The DOI string appears to be fabricated.

### `training_texas_method` ref 4

**Draft text:**  
`Stone MH et al. (2007). Periodization: effects of manipulating volume and intensity. Part 1. Strength Cond J, 29(1):56-62. doi:10.1519/1533-4295(2007)29[56:PEOMVA]2.0.CO;2`

**Fetch error:** `HTTP Error 404: Not Found`
**Notes:** Neither Crossref nor doi.org can resolve this DOI. The DOI string appears to be fabricated.

### `yt_training_volume_cut` ref 1

**Draft text:**  
`Baz-Valle E et al. (2024). The effects of exercise volume on muscle hypertrophy: updated systematic review and meta-analysis of 35 studies. Br J Sports Med. doi:10.1136/bjsports-2023-107803`

**Fetch error:** `HTTP Error 404: Not Found`
**Notes:** Neither Crossref nor doi.org can resolve this DOI. The DOI string appears to be fabricated.

### `yt_volume` ref 2

**Draft text:**  
`Baz-Valle E et al. (2024). The effects of exercise volume on muscle hypertrophy: updated systematic review and meta-analysis of 35 studies. Br J Sports Med. doi:10.1136/bjsports-2023-107803`

**Fetch error:** `HTTP Error 404: Not Found`
**Notes:** Neither Crossref nor doi.org can resolve this DOI. The DOI string appears to be fabricated.

## `DOI_WRONG` — 13 entries

_DOI resolves to a completely unrelated paper (different author and title). Either the DOI was copied from a random paper or fabricated to look plausible._

### `cardio_concurrent_training` ref 6

**Draft text:**  
`Fikenzer S et al. (2018). Effects of endurance versus resistance training on cardiac biomarkers. Clin Res Cardiol, 107(5):411-420. doi:10.1007/s00392-017-1192-0`

**What the DOI/PMID actually resolves to:**  
- First author: `Backhaus`  
- Year: `2017`  
- Title: `Management and predictors of outcome in unselected patients with cardiogenic shock complicating acute ST-segment elevation myocardial infarction: results from the Bremen STEMI Registry`  
- Journal: `Clinical Research in Cardiology`  
**Verification:** {'author_match': False, 'year_match': True, 'title_overlap': 0.0, 'journal_match': True}

### `cardio_zone2` ref 2

**Draft text:**  
`Fikenzer S et al. (2018). Effects of endurance versus resistance training on cardiac biomarkers in recreational athletes. Clin Res Cardiol, 107(5):411-420. doi:10.1007/s00392-017-1192-0`

**What the DOI/PMID actually resolves to:**  
- First author: `Backhaus`  
- Year: `2017`  
- Title: `Management and predictors of outcome in unselected patients with cardiogenic shock complicating acute ST-segment elevation myocardial infarction: results from the Bremen STEMI Registry`  
- Journal: `Clinical Research in Cardiology`  
**Verification:** {'author_match': False, 'year_match': True, 'title_overlap': 0.0, 'journal_match': True}

### `cardio_zone2` ref 5

**Draft text:**  
`Iellamo F et al. (2019). Cardiovascular effects of strength training in strength athletes. J Cardiovasc Med, 20(6):372-378. doi:10.2459/JCM.0000000000000648`

**What the DOI/PMID actually resolves to:**  
- First author: `Fortuni`  
- Year: `2018`  
- Title: `Closure of patent foramen ovale or medical therapy alone for secondary prevention of cryptogenic cerebrovascular events`  
- Journal: `Journal of Cardiovascular Medicine`  
**Verification:** {'author_match': False, 'year_match': True, 'title_overlap': 0.0, 'journal_match': True}

### `nutrition_caffeine_strength` ref 2

**Draft text:**  
`Ferreira TT et al. (2024). The effect of caffeine supplementation on muscular strength and endurance: A meta-analysis of meta-analyses. Heliyon, 10(19):e38529. doi:10.1016/j.heliyon.2024.e38529`

**What the DOI/PMID actually resolves to:**  
- First author: `Li`  
- Year: `2024`  
- Title: `Advances and trends in pressure ulcer care research over the last 20 years: A bibliometric and visual analysis`  
- Journal: `Heliyon`  
**Verification:** {'author_match': False, 'year_match': True, 'title_overlap': 0.0, 'journal_match': True}

### `nutrition_clean_eating_myth` ref 5

**Draft text:**  
`Del Corral P et al. (2009). Dietary adherence during weight loss predicts weight regain. Obesity, 17(6):1101-1103. doi:10.1038/oby.2009.35`

**What the DOI/PMID actually resolves to:**  
- First author: `Adéchian`  
- Year: `2009`  
- Title: `Excessive Energy Intake Does Not Modify Fed‐state Tissue Protein Synthesis Rates in Adult Rats`  
- Journal: `Obesity`  
**Verification:** {'author_match': False, 'year_match': True, 'title_overlap': 0.0, 'journal_match': True}

### `nutrition_omega3_recovery` ref 1

**Draft text:**  
`Tsuchiya Y et al. (2024). Omega-3 Fatty Acid Supplementation on Post-Exercise Inflammation, Muscle Damage, Oxidative Response, and Sports Performance in Physically Healthy Adults — A Systematic Review. Nutrients, 16(13):2017. doi:10.3390/nu16132017`

**What the DOI/PMID actually resolves to:**  
- First author: `Singh`  
- Year: `2024`  
- Title: `Efficacy of Pea Protein Supplementation in Combination with a Resistance Training Program on Muscle Performance in a Sedentary Adult Population: A Randomized, Comparator-Controlled, Parallel Clinical Trial`  
- Journal: `Nutrients`  
**Verification:** {'author_match': False, 'year_match': True, 'title_overlap': 0.2, 'journal_match': True}

### `nutrition_sleep_recovery` ref 1

**Draft text:**  
`Chen Y et al. (2025). Implications of sleep loss or sleep deprivation on muscle strength: a systematic review. PMC. doi:10.3390/nu17091452`

**What the DOI/PMID actually resolves to:**  
- First author: `Arnaoutis`  
- Year: `2025`  
- Title: `The Effect of Acute Dehydration upon Muscle Strength Indices at Elite Karate Athletes: A Randomized Crossover Study`  
- Journal: `Nutrients`  
**Verification:** {'author_match': False, 'year_match': True, 'title_overlap': 0.2, 'journal_match': True}

### `rehab_low_back_pain` ref 6

**Draft text:**  
`McGill SM et al. (2009). Exercises for the torso performed in a standing posture: spine and hip motion and motor patterns and spine load. J Strength Cond Res, 23(2):455-464. doi:10.1519/JSC.0b013e3181a0227e`

**What the DOI/PMID actually resolves to:**  
- First author: `Bradic`  
- Year: `2009`  
- Title: `Isokinetic Leg Strength Profile of Elite Male Basketball Players`  
- Journal: `Journal of Strength and Conditioning Research`  
**Verification:** {'author_match': False, 'year_match': True, 'title_overlap': 0.0, 'journal_match': True}

### `supplements_magnesium` ref 3

**Draft text:**  
`Veronese N et al. (2014). Effect of magnesium supplementation on glucose metabolism in people with or at risk of diabetes: a systematic review and meta-analysis. Eur J Clin Nutr, 68(12):1261-1272. doi:10.1038/ejcn.2014.209`

**What the DOI/PMID actually resolves to:**  
- First author: `Kearns`  
- Year: `2014`  
- Title: `The effect of a single, large bolus of vitamin D in healthy adults over the winter and following year: a randomized, double-blind, placebo-controlled trial`  
- Journal: `European Journal of Clinical Nutrition`  
**Verification:** {'author_match': False, 'year_match': True, 'title_overlap': 0.0, 'journal_match': True}

### `training_beginner_program` ref 2

**Draft text:**  
`Grgic J et al. (2018). The effects of short versus long inter-set rest intervals in resistance training on measures of muscle hypertrophy: a systematic review. Eur J Sport Sci, 18(7):971-980. doi:10.1080/17461391.2018.1444095`

**What the DOI/PMID actually resolves to:**  
- First author: `Mitchell`  
- Year: `2018`  
- Title: `Physiological implications of preparing for a natural male bodybuilding competition`  
- Journal: `European Journal of Sport Science`  
**Verification:** {'author_match': False, 'year_match': True, 'title_overlap': 0.0, 'journal_match': True}

### `yt_training_exercises` ref 1

**Draft text:**  
`Pedrosa GF et al. (2023). Training at long muscle lengths leads to greater muscle hypertrophy: a systematic review with meta-analysis. Med Sci Sports Exerc. doi:10.1249/MSS.0000000000003120`

**What the DOI/PMID actually resolves to:**  
- First author: `BARRY`  
- Year: `2023`  
- Title: `The Presence of Wind Worsens the Effect of Cold Temperature on Time to Ischemia in Patients with Stable Angina`  
- Journal: `Medicine &amp; Science in Sports &amp; Exercise`  
**Verification:** {'author_match': False, 'year_match': True, 'title_overlap': 0.0, 'journal_match': True}

### `yt_training_past_failure` ref 1

**Draft text:**  
`Vieira AF et al. (2024). Training to failure vs not to failure for muscle hypertrophy: a systematic review with meta-analysis. Scand J Med Sci Sports, 34(1):e14265. doi:10.1111/sms.14265`

**What the DOI/PMID actually resolves to:**  
- First author: `Juhász`  
- Year: `2022`  
- Title: `Short and mid‐term characteristics of COVID‐19 disease course in athletes: A high‐volume, single‐center study`  
- Journal: `Scandinavian Journal of Medicine &amp; Science in Sports`  
**Verification:** {'author_match': False, 'year_match': False, 'title_overlap': 0.0, 'journal_match': True}

### `yt_training_upper_body` ref 2

**Draft text:**  
`Pedrosa GF et al. (2023). Training at long muscle lengths leads to greater muscle hypertrophy. Med Sci Sports Exerc. doi:10.1249/MSS.0000000000003120`

**What the DOI/PMID actually resolves to:**  
- First author: `BARRY`  
- Year: `2023`  
- Title: `The Presence of Wind Worsens the Effect of Cold Temperature on Time to Ischemia in Patients with Stable Angina`  
- Journal: `Medicine &amp; Science in Sports &amp; Exercise`  
**Verification:** {'author_match': False, 'year_match': True, 'title_overlap': 0.0, 'journal_match': True}

## `DOI_MISATTRIBUTED` — 9 entries

_DOI resolves to a paper whose title matches the draft (>=80% word overlap) but the first author differs. Usually means the drafter invented a fake author name and attached it to a real paper's title + DOI._

### `nutrition_caffeine_strength` ref 1

**Draft text:**  
`Machado M et al. (2025). Effects of acute caffeine intake on muscular power during resistance exercise: a systematic review and meta-analysis. Front Nutr, 12:1686283. doi:10.3389/fnut.2025.1686283`

**What the DOI/PMID actually resolves to:**  
- First author: `Xiao`  
- Year: `2025`  
- Title: `Effects of acute caffeine intake on muscular power during resistance exercise: a systematic review and meta-analysis`  
- Journal: `Frontiers in Nutrition`  
**Verification:** {'author_match': False, 'year_match': True, 'title_overlap': 1.0, 'journal_match': True}

### `nutrition_caffeine_strength` ref 3

**Draft text:**  
`Grgic J et al. (2025). How does acute caffeine ingestion affect maximal strength and muscular power in bench press and back squat? J Int Soc Sports Nutr, 22(1):2587791. doi:10.1080/15502783.2025.2587791`

**What the DOI/PMID actually resolves to:**  
- First author: `Ma`  
- Year: `2025`  
- Title: `How does acute caffeine ingestion affect maximal strength and muscular power in bench press and back squat in resistance-trained men?`  
- Journal: `Journal of the International Society of Sports Nutrition`  
**Verification:** {'author_match': False, 'year_match': True, 'title_overlap': 0.867, 'journal_match': True}

### `nutrition_carb_timing` ref 1

**Draft text:**  
`Li Y et al. (2025). An investigation into how the timing of nutritional supplements affects the recovery from post-exercise fatigue: a systematic review and meta-analysis. Front Nutr, 12:1567438. doi:10.3389/fnut.2025.1567438`

**What the DOI/PMID actually resolves to:**  
- First author: `Cheng`  
- Year: `2025`  
- Title: `An investigation into how the timing of nutritional supplements affects the recovery from post-exercise fatigue: a systematic review and meta-analysis`  
- Journal: `Frontiers in Nutrition`  
**Verification:** {'author_match': False, 'year_match': True, 'title_overlap': 1.0, 'journal_match': True}

### `nutrition_omega3_recovery` ref 2

**Draft text:**  
`Harty PS et al. (2026). Improved muscle recovery after omega-3 supplementation is associated with increased oxylipin availability. Sci Rep. doi:10.1038/s41598-026-44339-1`

**What the DOI/PMID actually resolves to:**  
- First author: `Miranda-Fuentes`  
- Year: `2026`  
- Title: `Improved muscle recovery after omega-3 supplementation is associated with increased oxylipin availability`  
- Journal: `Scientific Reports`  
**Verification:** {'author_match': False, 'year_match': True, 'title_overlap': 1.0, 'journal_match': True}

### `nutrition_sleep_recovery` ref 2

**Draft text:**  
`Sayed A et al. (2025). Effects of sleep deprivation on sports performance and perceived exertion in athletes and non-athletes: a systematic review and meta-analysis. Front Physiol, 16:1544286. doi:10.3389/fphys.2025.1544286`

**What the DOI/PMID actually resolves to:**  
- First author: `Kong`  
- Year: `2025`  
- Title: `Effects of sleep deprivation on sports performance and perceived exertion in athletes and non-athletes: a systematic review and meta-analysis`  
- Journal: `Frontiers in Physiology`  
**Verification:** {'author_match': False, 'year_match': True, 'title_overlap': 1.0, 'journal_match': True}

### `nutrition_sleep_recovery` ref 3

**Draft text:**  
`Mavroudis C et al. (2025). Sleep and Athletic Performance: A Multidimensional Review of Physiological and Molecular Mechanisms. J Clin Med, 14(21):7606. doi:10.3390/jcm14217606`

**What the DOI/PMID actually resolves to:**  
- First author: `Kaczmarek`  
- Year: `2025`  
- Title: `Sleep and Athletic Performance: A Multidimensional Review of Physiological and Molecular Mechanisms`  
- Journal: `Journal of Clinical Medicine`  
**Verification:** {'author_match': False, 'year_match': True, 'title_overlap': 1.0, 'journal_match': True}

### `nutrition_vegan_creatine` ref 1

**Draft text:**  
`Forbes SC et al. (2025). Effects of Creatine Supplementation on Upper- and Lower-Body Strength and Power: A Systematic Review and Meta-Analysis. Nutrients, 17(17), 2748. doi:10.3390/nu17172748`

**What the DOI/PMID actually resolves to:**  
- First author: `Kazeminasab`  
- Year: `2025`  
- Title: `The Effects of Creatine Supplementation on Upper- and Lower-Body Strength and Power: A Systematic Review and Meta-Analysis`  
- Journal: `Nutrients`  
**Verification:** {'author_match': False, 'year_match': True, 'title_overlap': 1.0, 'journal_match': True}

### `nutrition_vegan_creatine` ref 2

**Draft text:**  
`Candow DG et al. (2024). Effects of Creatine Supplementation and Resistance Training on Muscle Strength Gains in Adults <50 Years: Systematic Review and Meta-Analysis. J Int Soc Sports Nutr, 21(1). PMID:39519498`

**What the DOI/PMID actually resolves to:**  
- First author: `Wang`  
- Year: `2024`  
- Title: `Effects of Creatine Supplementation and Resistance Training on Muscle Strength Gains in Adults <50 Years of Age: A Systematic Review and Meta-Analysis.`  
- Journal: `Nutrients`  
**Verification:** {'author_match': False, 'year_match': True, 'title_overlap': 1.0, 'journal_match': False}

### `nutrition_vitamin_d` ref 1

**Draft text:**  
`Farrokhyar F et al. (2024). Effects of vitamin D3 supplementation on strength of lower and upper extremities in athletes: an updated systematic review and meta-analysis of randomized controlled trials. Front Nutr, 11:1381301. doi:10.3389/fnut.2024.1381301`

**What the DOI/PMID actually resolves to:**  
- First author: `Han`  
- Year: `2024`  
- Title: `Effects of vitamin D3 supplementation on strength of lower and upper extremities in athletes: an updated systematic review and meta-analysis of randomized controlled trials`  
- Journal: `Frontiers in Nutrition`  
**Verification:** {'author_match': False, 'year_match': True, 'title_overlap': 1.0, 'journal_match': True}

## `NO_VERIFIABLE_SOURCE` — 21 entries

_No DOI, no PMID in the draft, and PubMed author+year+title search returned no hits. Cannot verify the paper exists. HIGH FABRICATION RISK._

### `nutrition_omega3_recovery` ref 3

**Draft text:**  
`Rossato LT et al. (2025). The Effect of Omega-3 on Mitigating Exercise-Induced Muscle Damage. Nutrients, 17(7):1234. PMC12044634`

**Notes:** No DOI, no PMID in the draft, and PubMed search on (first_author, year, title keywords) returned no hits.

### `nutrition_omega3_recovery` ref 4

**Draft text:**  
`Da Boit M et al. (2024). Omega-3 Fatty Acids and Muscle Strength — Current State of Knowledge and Future Perspectives. Nutrients, 16(22):3408. PMC11643269`

**Notes:** No DOI, no PMID in the draft, and PubMed search on (first_author, year, title keywords) returned no hits.

### `nutrition_whey_vs_collagen` ref 5

**Draft text:**  
`de Sire A et al. (2022). Systematic review on collagen supplementation: lack of high-quality evidence for skin and joint outcomes.`

**Notes:** No DOI, no PMID in the draft, and PubMed search on (first_author, year, title keywords) returned no hits.

### `training_bench_mistakes` ref 1

**Draft text:**  
`Green CM & Comfort P (2007). Effect of grip width on bench press performance and risk of injury. Strength Cond J, 29(5):10-14.`

**Notes:** No DOI, no PMID in the draft, and PubMed search on (first_author, year, title keywords) returned no hits.

### `training_squat_mistakes` ref 3

**Draft text:**  
`Kritz M et al. (2009). The bodyweight squat: a movement screen for the squat pattern. Strength Cond J, 31(1):76-85.`

**Notes:** No DOI, no PMID in the draft, and PubMed search on (first_author, year, title keywords) returned no hits.

### `training_squat_mistakes` ref 4

**Draft text:**  
`Comfort P et al. (2018). Effect of knee and trunk angle on kinetic variables during the isometric midthigh pull. Int J Sports Physiol Perform, 13(5):575-581.`

**Notes:** No DOI, no PMID in the draft, and PubMed search on (first_author, year, title keywords) returned no hits.

### `training_warmups` ref 3

**Draft text:**  
`Barroso R et al. (2013). Maximal strength, number of repetitions, and total volume are differently affected by static-, ballistic-, and proprioceptive neuromuscular facilitation stretching. J Strength Cond Res, 27(10):2903-2908.`

**Notes:** No DOI, no PMID in the draft, and PubMed search on (first_author, year, title keywords) returned no hits.

### `yt_bench_shoulder_injury` ref 1

**Draft text:**  
`Green CM & Comfort P (2007). Effect of grip width on bench press performance and risk of injury. Strength Cond J, 29(5):10-14.`

**Notes:** No DOI, no PMID in the draft, and PubMed search on (first_author, year, title keywords) returned no hits.

### `yt_bench_shoulder_injury` ref 5

**Draft text:**  
`Durall CJ et al. (2012). Shoulder injury prevention tips for overhead pressing. Strength Cond J, 34(1):24-29.`

**Notes:** No DOI, no PMID in the draft, and PubMed search on (first_author, year, title keywords) returned no hits.

### `yt_deadlift_accessories` ref 2

**Draft text:**  
`Robbins DW et al. (2012). The effect of a Romanian deadlift exercise on multijoint muscle strength characteristics. J Strength Cond Res, 26(12):3321-3328.`

**Notes:** No DOI, no PMID in the draft, and PubMed search on (first_author, year, title keywords) returned no hits.

### `yt_deadlift_accessories` ref 5

**Draft text:**  
`Stastny P et al. (2017). Strengthening the gluteus medius using various bodyweight and resistance exercises. Strength Cond J, 38(3):91-98.`

**Notes:** No DOI, no PMID in the draft, and PubMed search on (first_author, year, title keywords) returned no hits.

### `yt_powerlifting_program` ref 3

**Draft text:**  
`Pritchard H et al. (2015). Tapering practices of competitive powerlifters. J Strength Cond Res, 29(7):1867-1872.`

**Notes:** No DOI, no PMID in the draft, and PubMed search on (first_author, year, title keywords) returned no hits.

### `yt_powerlifting_program` ref 4

**Draft text:**  
`Stone MH et al. (2007). Periodization: effects of manipulating volume and intensity. Part 1. Strength Cond J, 21(2):56-62.`

**Notes:** No DOI, no PMID in the draft, and PubMed search on (first_author, year, title keywords) returned no hits.

### `yt_powerlifting_program` ref 5

**Draft text:**  
`Helms ER et al. (2015). Application of the repetitions in reserve-based rating of perceived exertion scale for resistance training. Strength Cond J, 38(4):42-49.`

**Notes:** No DOI, no PMID in the draft, and PubMed search on (first_author, year, title keywords) returned no hits.

### `yt_protein_excess` ref 4

**Draft text:**  
`Bagheri R et al. (2024). Even protein distribution enhances weekly muscle protein synthesis by ~12%. Front Nutr.`

**Notes:** No DOI, no PMID in the draft, and PubMed search on (first_author, year, title keywords) returned no hits.

### `yt_training_exercises` ref 2

**Draft text:**  
`Chavez ML et al. (2023). Incline vs flat bench press: effect on muscle activation and hypertrophy. J Strength Cond Res.`

**Notes:** No DOI, no PMID in the draft, and PubMed search on (first_author, year, title keywords) returned no hits.

### `yt_training_past_failure` ref 3

**Draft text:**  
`Schoenfeld BJ & Grgic J (2019). Does training to failure maximize muscle hypertrophy? Strength Cond J, 41(5):108-113.`

**Notes:** No DOI, no PMID in the draft, and PubMed search on (first_author, year, title keywords) returned no hits.

### `yt_training_past_failure` ref 5

**Draft text:**  
`Lacerda LT et al. (2020). Variations in repetition duration and repetition numbers influence muscular activation and blood lactate response in protocols equalized by time under tension. J Strength Cond Res, 34(4):952-960.`

**Notes:** No DOI, no PMID in the draft, and PubMed search on (first_author, year, title keywords) returned no hits.

### `yt_training_upper_body` ref 1

**Draft text:**  
`Chavez ML et al. (2023). Effect of incline angle on upper and lower pectoral muscle activation during bench press. J Strength Cond Res.`

**Notes:** No DOI, no PMID in the draft, and PubMed search on (first_author, year, title keywords) returned no hits.

### `yt_training_upper_body` ref 3

**Draft text:**  
`Schoenfeld BJ et al. (2021). Resistance training recommendations to maximize muscle hypertrophy in an athletic population. Strength Cond J, 43(4):3-13.`

**Notes:** No DOI, no PMID in the draft, and PubMed search on (first_author, year, title keywords) returned no hits.

### `yt_volume` ref 5

**Draft text:**  
`Hackett DA et al. (2018). Effect of increasing the volume of training on resistance training-related outcomes. J Strength Cond Res, 32(5):1254-1262.`

**Notes:** No DOI, no PMID in the draft, and PubMed search on (first_author, year, title keywords) returned no hits.

## `YEAR_WRONG` — 1 entry

_Author and title match but publication year is off by >1 from the draft._

### `supplements_magnesium` ref 7

**Draft text:**  
`Reno AM et al. (2022). Effects of magnesium supplementation on muscle soreness and performance. J Strength Cond Res, 36(8):2198-2203. doi:10.1519/JSC.0000000000003827`

**What the DOI/PMID actually resolves to:**  
- First author: `Reno`  
- Year: `2020`  
- Title: `Effects of Magnesium Supplementation on Muscle Soreness and Performance`  
- Journal: `Journal of Strength &amp; Conditioning Research`  
**Verification:** {'author_match': True, 'year_match': False, 'title_overlap': 1.0, 'journal_match': True}

## `JOURNAL_MISMATCH` — 5 entries

_Everything else matches but the cited journal differs from the actual venue. Minor error — usually the drafter recorded the wrong journal name for a real paper._

### `nutrition_clean_eating_myth` ref 3

**Draft text:**  
`Stice E et al. (2008). Relation of obesity to consummatory and anticipatory food reward. Physiol Behav, 97(5):551-560.`

**What the DOI/PMID actually resolves to:**  
- First author: `Stice`  
- Year: `2008`  
- Title: `Relation of reward from food intake and anticipated food intake to obesity: a functional magnetic resonance imaging study.`  
- Journal: `Journal of abnormal psychology`  
**Verification:** {'author_match': True, 'year_match': True, 'title_overlap': 0.4, 'journal_match': False}
**Notes:** Matched via PubMed author+year+title search (no DOI in draft). PMID=19025237

### `training_masters_lifters` ref 5

**Draft text:**  
`Morton RW et al. (2018). Protein supplementation and resistance training gains in older adults. Br J Sports Med, 52(6):376-384.`

**What the DOI/PMID actually resolves to:**  
- First author: `Morton`  
- Year: `2018`  
- Title: `Does protein supplementation really augment hypertrophy in older persons with resistance exercise training?`  
- Journal: `The American journal of clinical nutrition`  
**Verification:** {'author_match': True, 'year_match': True, 'title_overlap': 0.455, 'journal_match': False}
**Notes:** Matched via PubMed author+year+title search (no DOI in draft). PMID=29771273

### `yt_training_exercises` ref 3

**Draft text:**  
`Schoenfeld BJ & Grgic J (2020). Effects of range of motion on muscle development during resistance training. J Strength Cond Res, 34(5):1441-1453.`

**What the DOI/PMID actually resolves to:**  
- First author: `Schoenfeld`  
- Year: `2020`  
- Title: `Effects of range of motion on muscle development during resistance training interventions: A systematic review.`  
- Journal: `SAGE open medicine`  
**Verification:** {'author_match': True, 'year_match': True, 'title_overlap': 0.875, 'journal_match': False}
**Notes:** Matched via PubMed author+year+title search (no DOI in draft). PMID=32030125

### `yt_training_volume_cut` ref 3

**Draft text:**  
`Heaselgrave SR et al. (2019). Dose-response of weekly resistance training volume on muscular adaptations. Med Sci Sports Exerc, 51(5):1033-1040.`

**What the DOI/PMID actually resolves to:**  
- First author: `Heaselgrave`  
- Year: `2019`  
- Title: `Dose-Response Relationship of Weekly Resistance-Training Volume and Frequency on Muscular Adaptations in Trained Men.`  
- Journal: `International journal of sports physiology and performance`  
**Verification:** {'author_match': True, 'year_match': True, 'title_overlap': 0.727, 'journal_match': False}
**Notes:** Matched via PubMed author+year+title search (no DOI in draft). PMID=30160627

### `yt_volume` ref 3

**Draft text:**  
`Heaselgrave SR et al. (2019). Dose-response relationship of weekly resistance training volume and frequency on muscular adaptations. Med Sci Sports Exerc, 51(5):1033-1040.`

**What the DOI/PMID actually resolves to:**  
- First author: `Heaselgrave`  
- Year: `2019`  
- Title: `Dose-Response Relationship of Weekly Resistance-Training Volume and Frequency on Muscular Adaptations in Trained Men.`  
- Journal: `International journal of sports physiology and performance`  
**Verification:** {'author_match': True, 'year_match': True, 'title_overlap': 0.909, 'journal_match': False}
**Notes:** Matched via PubMed author+year+title search (no DOI in draft). PMID=30160627

## `NOT_PUBMED_INDEXED` — 6 entries

_Textbook / institutional report / YouTube video / non-peer-reviewed source. Not verifiable via Crossref/PubMed. Editor must confirm by hand._

### `nutrition_omega3_recovery` ref 5

**Draft text:**  
`Gatorade Sports Science Institute (2024). Omega-3 Fatty Acids for Training Adaptation and Exercise Recovery: A Muscle-Centric Perspective in Athletes. GSSI.`

**Notes:** Textbook / institutional report / YouTube video / non-peer-reviewed source. Not verifiable via Crossref/PubMed. Editor should confirm the source exists and the quoted figures are accurate by hand.

### `nutrition_vegan_creatine` ref 4

**Draft text:**  
`ACE Fitness (2025). Creatine Reconsidered: What the Latest Research Reveals.`

**Notes:** Textbook / institutional report / YouTube video / non-peer-reviewed source. Not verifiable via Crossref/PubMed. Editor should confirm the source exists and the quoted figures are accurate by hand.

### `rehab_low_back_pain` ref 3

**Draft text:**  
`McGill SM (2015). Low Back Disorders: Evidence-Based Prevention and Rehabilitation, 3rd Edition. Human Kinetics.`

**Notes:** Textbook / institutional report / YouTube video / non-peer-reviewed source. Not verifiable via Crossref/PubMed. Editor should confirm the source exists and the quoted figures are accurate by hand.

### `training_beginner_program` ref 5

**Draft text:**  
`NSCA (2024). Essentials of Strength Training and Conditioning, 5th Edition. Chapter 19: Program Design for Resistance Training.`

**Notes:** Textbook / institutional report / YouTube video / non-peer-reviewed source. Not verifiable via Crossref/PubMed. Editor should confirm the source exists and the quoted figures are accurate by hand.

### `yt_training_exercises` ref 5

**Draft text:**  
`Nippard J (2025). 7 Amazing Exercises No One Does. YouTube.`

**Notes:** Textbook / institutional report / YouTube video / non-peer-reviewed source. Not verifiable via Crossref/PubMed. Editor should confirm the source exists and the quoted figures are accurate by hand.

### `yt_training_upper_body` ref 5

**Draft text:**  
`Nippard J (2025). The Upper Body Workout I Followed For My 1 Year Transformation. YouTube.`

**Notes:** Textbook / institutional report / YouTube video / non-peer-reviewed source. Not verifiable via Crossref/PubMed. Editor should confirm the source exists and the quoted figures are accurate by hand.

---
## Method appendix

Implementation: `audits/_citation_audit.py` (importable, CSKB F-0 gate-ready).

**Parser:** regex over `REFERENCES:` block. Extracts `first_author` surname, `year`, `title`, `doi`, `pmid`, and `journal` from each line. Handles two-word surnames (e.g. "Del Corral"), co-author stripping (`& Van Cauter E`), and non-author-prefixed entries (title-first format).

**DOI verification:** Crossref API. On HTTP 404, falls back to `HEAD https://doi.org/<doi>` — if that also 404s, classify as `DOI_FABRICATED`; if doi.org accepts it, classify as `DOI_UNRESOLVABLE` (soft flag, may be Crossref lag).

**PMID verification:** NCBI esummary.

**No-DOI verification:** PubMed esearch with `{author}[AU] AND {year}[dp] AND ({top 6 title keywords})`, then esummary on the top hit. Match requires same classify() pass.

**Verification rule (`classify()`):**
- `author_match` = draft surname == Crossref first author surname (diacritic-normalized, hyphen-stripped, case-insensitive)
- `year_match` = |draft year − fetched year| ≤ 1
- `title_overlap` = Jaccard of stopword-filtered 4+ char tokens between draft title and fetched title; must be ≥0.25
- `journal_match` = shared informative tokens in j_tokens(draft_journal) ∩ j_tokens(fetched_journal); ≥2 shared or ≥50% overlap on the smaller set

**Stopword list** (`STOPWORDS` in the script): the, and, for, with, from, into, over, under, between, among, more, less, than, that, this, these, those, their, there, which, where, when, what, have, has, been, were, are, was, is, a, an, of, in, on, to, by, as, at, be, or, vs, versus, systematic, review, meta-analysis, meta, analysis, effect, effects, influence, impact, results, study, studies, trial, trials, randomized, randomised, controlled, double-blind, placebo, position, stand, narrative, gains, recommendations, recommendation, based, evidence.

**Non-academic source detection:** regex over the raw reference text matches YouTube, ACE Fitness, NSCA Essentials textbook, "Nth Edition", Gatorade SSI, Nippard, etc. These short-circuit to `NOT_PUBMED_INDEXED` instead of attempting fruitless PubMed search.

**Contact / UA:** `mailto:contentprinter@centralstrengthgyms.com`, user-agent `ContentPrinter/0.1 (mailto:contentprinter@centralstrengthgyms.com)`.

**Known limitations:**
1. `NO_VERIFIABLE_SOURCE` is noisier than `DOI_FABRICATED` — a missed PubMed search could be index lag or the paper existing under a slightly different title. Each entry needs manual spot-check before deciding to drop/replace.
2. Journal abbreviation matching uses a hand-curated expansion table. If it flags `JOURNAL_MISMATCH` on two obviously-synonymous names, add the abbreviation to `JOURNAL_ABBR` in the script and re-run.
3. Crossref lag: a DOI deposited this week may 404 from Crossref for up to 48h. The doi.org HEAD fallback catches this and downgrades to `DOI_UNRESOLVABLE`.
4. Author-less reference lines (title-first format, seen in `rehab_shoulder_prehab`) are parsed but author_match is `None`, so they skip the author check. Title+DOI+journal match alone determines severity.

**For CentralStrengthKB Objective F-0:** import `audit_draft(draft_text, slug)` from this module. Return value is a list of row dicts. Job-runner gate: fail the job if any row has severity in `{DOI_FABRICATED, DOI_WRONG, DOI_MISATTRIBUTED, NO_VERIFIABLE_SOURCE, PMID_NOT_FOUND, AUTHOR_WRONG, TITLE_MISMATCH}`. `JOURNAL_MISMATCH`, `YEAR_WRONG`, `NOT_PUBMED_INDEXED`, and `DOI_UNRESOLVABLE` are soft flags that should surface in the iOS UI but not block the job.
