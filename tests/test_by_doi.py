import unittest
import xml.etree.ElementTree as ET

from src.fetchers.by_doi import fetch_by_doi

# Minimal Crossref /works/{doi} "message" item
CR_WITH_ABSTRACT = {
    "DOI": "10.1/withabs",
    "title": ["Crossref Title"],
    "author": [{"given": "Jane", "family": "Doe"}],
    "container-title": ["Radiology"],
    "published-online": {"date-parts": [[2026, 7, 4]]},
    "abstract": "<p>Crossref abstract text.</p>",
}
CR_NO_ABSTRACT = {
    "DOI": "10.1/noabs",
    "title": ["Crossref Title 2"],
    "author": [{"given": "John", "family": "Roe"}],
    "container-title": ["JMRI"],
    "published-online": {"date-parts": [[2026, 7, 5]]},
}

# Minimal PubmedArticle element with an abstract
PM_XML = """
<PubmedArticle>
  <MedlineCitation>
    <Article>
      <ArticleTitle>PubMed Title</ArticleTitle>
      <Abstract><AbstractText>PubMed abstract text.</AbstractText></Abstract>
      <AuthorList><Author><LastName>Smith</LastName><Initials>A</Initials></Author></AuthorList>
      <Journal><Title>Gut</Title>
        <JournalIssue><PubDate><Year>2026</Year><Month>Jul</Month><Day>5</Day></PubDate></JournalIssue>
      </Journal>
    </Article>
  </MedlineCitation>
  <PubmedData><ArticleIdList>
    <ArticleId IdType="doi">10.1/noabs</ArticleId>
  </ArticleIdList></PubmedData>
</PubmedArticle>
"""


class TestFetchByDoi(unittest.TestCase):
    def test_crossref_with_abstract_returns_full_dict(self):
        p = fetch_by_doi(
            "10.1/withabs", "e@x.com", None,
            crossref=lambda d, e: CR_WITH_ABSTRACT,
            pubmed=lambda d, k, e: None,
        )
        self.assertEqual(p["doi"], "10.1/withabs")
        self.assertEqual(p["title"], "Crossref Title")
        self.assertEqual(p["journal"], "Radiology")
        self.assertEqual(p["pub_date"], "2026-07-04")
        self.assertIn("Crossref abstract", p["abstract"])
        self.assertEqual(p["source"], "crossref-rehydrate")

    def test_falls_back_to_pubmed_when_crossref_has_no_abstract(self):
        p = fetch_by_doi(
            "10.1/noabs", "e@x.com", "key",
            crossref=lambda d, e: CR_NO_ABSTRACT,
            pubmed=lambda d, k, e: ET.fromstring(PM_XML),
        )
        self.assertIn("PubMed abstract", p["abstract"])
        self.assertEqual(p["source"], "pubmed")

    def test_no_abstract_anywhere_returns_crossref_with_null_abstract(self):
        p = fetch_by_doi(
            "10.1/noabs", "e@x.com", "key",
            crossref=lambda d, e: CR_NO_ABSTRACT,
            pubmed=lambda d, k, e: None,
        )
        self.assertEqual(p["doi"], "10.1/noabs")
        self.assertIsNone(p["abstract"])
        self.assertEqual(p["source"], "crossref-rehydrate")

    def test_unresolvable_doi_returns_none(self):
        p = fetch_by_doi(
            "10.1/gone", "e@x.com", "key",
            crossref=lambda d, e: None,
            pubmed=lambda d, k, e: None,
        )
        self.assertIsNone(p)
