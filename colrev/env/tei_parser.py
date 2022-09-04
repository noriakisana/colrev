#! /usr/bin/env python
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import requests
from lxml import etree

import colrev.env.grobid_service
import colrev.exceptions as colrev_exceptions
import colrev.process
import colrev.record

if TYPE_CHECKING:
    import colrev.review_manager.ReviewManager


class TEIParser:
    ns = {
        "tei": "{http://www.tei-c.org/ns/1.0}",
        "w3": "{http://www.w3.org/XML/1998/namespace}",
    }
    nsmap = {
        "tei": "http://www.tei-c.org/ns/1.0",
        "w3": "http://www.w3.org/XML/1998/namespace",
    }

    def __init__(
        self,
        *,
        pdf_path: Path = None,
        tei_path: Path = None,
    ):
        """Creates a TEI file
        modes of operation:
        - pdf_path: create TEI and temporarily store in self.data
        - pfd_path and tei_path: create TEI and save in tei_path
        - tei_path: read TEI from file
        """

        # pylint: disable=consider-using-with
        assert pdf_path is not None or tei_path is not None
        if pdf_path is not None:
            if pdf_path.is_symlink():
                pdf_path = pdf_path.resolve()
        self.pdf_path = pdf_path
        self.tei_path = tei_path
        if pdf_path is not None:
            assert pdf_path.is_file()
        else:
            assert tei_path.is_file()  # type: ignore

        load_from_tei = False
        if tei_path is not None:
            if tei_path.is_file():
                load_from_tei = True

        if pdf_path is not None and not load_from_tei:
            grobid_service = colrev.env.grobid_service.GrobidService()
            grobid_service.start()
            # Note: we have more control and transparency over the consolidation
            # if we do it in the colrev process
            options = {}
            options["consolidateHeader"] = "0"
            options["consolidateCitations"] = "0"
            try:
                ret = requests.post(
                    colrev.env.grobid_service.GrobidService.GROBID_URL
                    + "/api/processFulltextDocument",
                    files={"input": open(str(pdf_path), "rb")},
                    data=options,
                )

                # Possible extension: get header only (should be more efficient)
                # r = requests.post(
                #     GrobidService.GROBID_URL + "/api/processHeaderDocument",
                #     files=dict(input=open(filepath, "rb")),
                #     data=header_data,
                # )

                if ret.status_code != 200:
                    raise colrev_exceptions.TEIException()

                if b"[TIMEOUT]" in ret.content:
                    raise colrev_exceptions.TEITimeoutException()

                self.root = etree.fromstring(ret.content)

                if tei_path is not None:
                    tei_path.parent.mkdir(exist_ok=True, parents=True)
                    with open(tei_path, "wb") as file:
                        file.write(ret.content)

                    # Note : reopen/write to prevent format changes in the enhancement
                    with open(tei_path, "rb") as file:
                        xml_fstring = file.read()
                    self.root = etree.fromstring(xml_fstring)

                    tree = etree.ElementTree(self.root)
                    tree.write(str(tei_path), pretty_print=True, encoding="utf-8")
            except requests.exceptions.ConnectionError as exc:
                print(exc)
                print(str(pdf_path))
        elif tei_path is not None:
            with open(tei_path, encoding="utf-8") as file:
                xml_string = file.read()
            if "[BAD_INPUT_DATA]" in xml_string[:100]:
                raise colrev_exceptions.TEIException()
            self.root = etree.fromstring(xml_string)

    def get_tei_str(self) -> str:
        return etree.tostring(self.root).decode("utf-8")

    def __get_paper_title(self) -> str:
        title_text = "NA"
        file_description = self.root.find(".//" + self.ns["tei"] + "fileDesc")
        if file_description is not None:
            title_stmt_node = file_description.find(
                ".//" + self.ns["tei"] + "titleStmt"
            )
            if title_stmt_node is not None:
                title_node = title_stmt_node.find(".//" + self.ns["tei"] + "title")
                if title_node is not None:
                    title_text = (
                        title_node.text if title_node.text is not None else "NA"
                    )
                    title_text = (
                        title_text.replace("(Completed paper)", "")
                        .replace("(Completed-paper)", "")
                        .replace("(Research-in-Progress)", "")
                        .replace("Completed Research Paper", "")
                    )
        return title_text

    def __get_paper_journal(self) -> str:
        journal_name = "NA"
        file_description = self.root.find(".//" + self.ns["tei"] + "sourceDesc")
        if file_description is not None:
            if file_description.find(".//" + self.ns["tei"] + "monogr") is not None:
                journal_node = file_description.find(".//" + self.ns["tei"] + "monogr")
                if journal_node is not None:
                    jtitle_node = journal_node.find(".//" + self.ns["tei"] + "title")
                    if jtitle_node is not None:
                        journal_name = (
                            jtitle_node.text if jtitle_node.text is not None else "NA"
                        )
                        if "NA" != journal_name:
                            words = journal_name.split()
                            if sum(word.isupper() for word in words) / len(words) > 0.8:
                                words = [word.capitalize() for word in words]
                                journal_name = " ".join(words)
        return journal_name

    def __get_paper_journal_volume(self) -> str:
        volume = "NA"
        file_description = self.root.find(".//" + self.ns["tei"] + "sourceDesc")
        if file_description is not None:
            if file_description.find(".//" + self.ns["tei"] + "monogr") is not None:
                journal_node = file_description.find(".//" + self.ns["tei"] + "monogr")
                if journal_node is not None:
                    imprint_node = journal_node.find(".//" + self.ns["tei"] + "imprint")
                    if imprint_node is not None:
                        vnode = imprint_node.find(
                            ".//" + self.ns["tei"] + "biblScope[@unit='volume']"
                        )
                        if vnode is not None:
                            volume = vnode.text if vnode.text is not None else "NA"
        return volume

    def __get_paper_journal_issue(self) -> str:
        issue = "NA"
        file_description = self.root.find(".//" + self.ns["tei"] + "sourceDesc")
        if file_description is not None:
            if file_description.find(".//" + self.ns["tei"] + "monogr") is not None:
                journal_node = file_description.find(".//" + self.ns["tei"] + "monogr")
                if journal_node is not None:
                    imprint_node = journal_node.find(".//" + self.ns["tei"] + "imprint")
                    if imprint_node is not None:
                        issue_node = imprint_node.find(
                            ".//" + self.ns["tei"] + "biblScope[@unit='issue']"
                        )
                        if issue_node is not None:
                            issue = (
                                issue_node.text if issue_node.text is not None else "NA"
                            )
        return issue

    def __get_paper_journal_pages(self) -> str:
        pages = "NA"
        file_description = self.root.find(".//" + self.ns["tei"] + "sourceDesc")
        if file_description is not None:
            journal_node = file_description.find(".//" + self.ns["tei"] + "monogr")
            if journal_node is not None:
                imprint_node = journal_node.find(".//" + self.ns["tei"] + "imprint")
                if imprint_node is not None:
                    page_node = imprint_node.find(
                        ".//" + self.ns["tei"] + "biblScope[@unit='page']"
                    )
                    if page_node is not None:
                        if (
                            page_node.get("from") is not None
                            and page_node.get("to") is not None
                        ):
                            pages = (
                                page_node.get("from", "")
                                + "--"
                                + page_node.get("to", "")
                            )
        return pages

    def __get_paper_year(self) -> str:
        year = "NA"
        file_description = self.root.find(".//" + self.ns["tei"] + "sourceDesc")
        if file_description is not None:
            if file_description.find(".//" + self.ns["tei"] + "monogr") is not None:
                journal_node = file_description.find(".//" + self.ns["tei"] + "monogr")
                if journal_node is not None:
                    imprint_node = journal_node.find(".//" + self.ns["tei"] + "imprint")
                    if imprint_node is not None:
                        date_node = imprint_node.find(".//" + self.ns["tei"] + "date")
                        if date_node is not None:
                            year = (
                                date_node.get("when", "")
                                if date_node.get("when") is not None
                                else "NA"
                            )
                            year = re.sub(r".*([1-2][0-9]{3}).*", r"\1", year)
        return year

    def get_author_name_from_node(self, *, author_node) -> str:
        authorname = ""

        author_pers_node = author_node.find(self.ns["tei"] + "persName")
        if author_pers_node is None:
            return authorname
        surname_node = author_pers_node.find(self.ns["tei"] + "surname")
        if surname_node is not None:
            surname = surname_node.text if surname_node.text is not None else ""
        else:
            surname = ""

        forename_node = author_pers_node.find(
            self.ns["tei"] + 'forename[@type="first"]'
        )
        if forename_node is not None:
            forename = forename_node.text if forename_node.text is not None else ""
        else:
            forename = ""

        if 1 == len(forename):
            forename = forename + "."

        middlename_node = author_pers_node.find(
            self.ns["tei"] + 'forename[@type="middle"]'
        )
        if middlename_node is not None:
            middlename = (
                " " + middlename_node.text if middlename_node.text is not None else ""
            )
        else:
            middlename = ""

        if 1 == len(middlename):
            middlename = middlename + "."

        authorname = surname + ", " + forename + middlename

        authorname = (
            authorname.replace("\n", " ")
            .replace("\r", "")
            .replace("•", "")
            .replace("+", "")
            .replace("Dipl.", "")
            .replace("Prof.", "")
            .replace("Dr.", "")
            .replace("&apos", "'")
            .replace("❚", "")
            .replace("~", "")
            .replace("®", "")
            .replace("|", "")
        )

        authorname = re.sub("^Paper, Short; ", "", authorname)
        return authorname

    def __get_paper_authors(self) -> str:
        author_string = "NA"
        file_description = self.root.find(".//" + self.ns["tei"] + "sourceDesc")
        author_list = []

        if file_description is not None:
            if file_description.find(".//" + self.ns["tei"] + "analytic") is not None:
                analytic_node = file_description.find(
                    ".//" + self.ns["tei"] + "analytic"
                )
                if analytic_node is not None:
                    for author_node in analytic_node.iterfind(
                        self.ns["tei"] + "author"
                    ):

                        authorname = self.get_author_name_from_node(
                            author_node=author_node
                        )
                        if authorname in ["Paper, Short"]:
                            continue
                        if authorname not in [", ", ""]:
                            author_list.append(authorname)

                    author_string = " and ".join(author_list)

                    if author_string is None:
                        author_string = "NA"
                    if "" == author_string.replace(" ", "").replace(",", "").replace(
                        ";", ""
                    ):
                        author_string = "NA"
        return author_string

    def __get_paper_doi(self) -> str:
        doi = "NA"
        file_description = self.root.find(".//" + self.ns["tei"] + "sourceDesc")
        if file_description is not None:
            bibl_struct = file_description.find(".//" + self.ns["tei"] + "biblStruct")
            if bibl_struct is not None:
                dois = bibl_struct.findall(".//" + self.ns["tei"] + "idno[@type='DOI']")
                for res in dois:
                    if res.text is not None:
                        doi = res.text
        return doi

    def get_abstract(self) -> str:

        html_tag_regex = re.compile("<.*?>")

        def cleanhtml(raw_html):
            cleantext = re.sub(html_tag_regex, "", raw_html)
            return cleantext

        abstract_text = "NA"
        profile_description = self.root.find(".//" + self.ns["tei"] + "profileDesc")
        if profile_description is not None:
            abstract_node = profile_description.find(
                ".//" + self.ns["tei"] + "abstract"
            )
            html_str = etree.tostring(abstract_node).decode("utf-8")
            abstract_text = cleanhtml(html_str)
        return abstract_text

    def get_metadata(self) -> dict:

        record = {
            "ENTRYTYPE": "article",
            "title": self.__get_paper_title(),
            "author": self.__get_paper_authors(),
            "journal": self.__get_paper_journal(),
            "year": self.__get_paper_year(),
            "volume": self.__get_paper_journal_volume(),
            "number": self.__get_paper_journal_issue(),
            "pages": self.__get_paper_journal_pages(),
            "doi": self.__get_paper_doi(),
        }

        for key, value in record.items():
            if "file" != key:
                record[key] = value.replace("}", "").replace("{", "").rstrip("\\")
            else:
                print(f"problem in filename: {key}")

        return record

    def get_paper_keywords(self) -> list:
        keywords = []
        for keyword_list in self.root.iter(self.ns["tei"] + "keywords"):
            for keyword in keyword_list.iter(self.ns["tei"] + "term"):
                keywords.append(keyword.text)
        return keywords

    # (individual) bibliography-reference elements  ----------------------------

    def __get_reference_bibliography_id(self, *, reference) -> str:
        if "ID" in reference.attrib:
            return reference.attrib["ID"]
        return ""

    def __get_reference_bibliography_tei_id(self, *, reference) -> str:
        return reference.attrib[self.ns["w3"] + "id"]

    def __get_reference_author_string(self, *, reference) -> str:
        author_list = []
        if reference.find(self.ns["tei"] + "analytic") is not None:
            authors_node = reference.find(self.ns["tei"] + "analytic")
        elif reference.find(self.ns["tei"] + "monogr") is not None:
            authors_node = reference.find(self.ns["tei"] + "monogr")

        for author_node in authors_node.iterfind(self.ns["tei"] + "author"):

            authorname = self.get_author_name_from_node(author_node=author_node)

            if authorname not in [", ", ""]:
                author_list.append(authorname)

        author_string = " and ".join(author_list)

        author_string = (
            author_string.replace("\n", " ")
            .replace("\r", "")
            .replace("•", "")
            .replace("+", "")
            .replace("Dipl.", "")
            .replace("Prof.", "")
            .replace("Dr.", "")
            .replace("&apos", "'")
            .replace("❚", "")
            .replace("~", "")
            .replace("®", "")
            .replace("|", "")
        )

        if author_string is None:
            author_string = "NA"
        if "" == author_string.replace(" ", "").replace(",", "").replace(";", ""):
            author_string = "NA"
        return author_string

    def __get_reference_title_string(self, *, reference) -> str:
        title_string = ""
        if reference.find(self.ns["tei"] + "analytic") is not None:
            title = reference.find(self.ns["tei"] + "analytic").find(
                self.ns["tei"] + "title"
            )
        elif reference.find(self.ns["tei"] + "monogr") is not None:
            title = reference.find(self.ns["tei"] + "monogr").find(
                self.ns["tei"] + "title"
            )
        if title is None:
            title_string = "NA"
        else:
            title_string = title.text
        return title_string

    def __get_reference_year_string(self, *, reference) -> str:
        year_string = ""
        if reference.find(self.ns["tei"] + "monogr") is not None:
            year = (
                reference.find(self.ns["tei"] + "monogr")
                .find(self.ns["tei"] + "imprint")
                .find(self.ns["tei"] + "date")
            )
        elif reference.find(self.ns["tei"] + "analytic") is not None:
            year = (
                reference.find(self.ns["tei"] + "analytic")
                .find(self.ns["tei"] + "imprint")
                .find(self.ns["tei"] + "date")
            )

        if year is not None:
            for name, value in sorted(year.items()):
                if name == "when":
                    year_string = value
                else:
                    year_string = "NA"
        else:
            year_string = "NA"
        return year_string

    def __get_reference_page_string(self, *, reference) -> str:
        page_string = ""

        if reference.find(self.ns["tei"] + "monogr") is not None:
            page_list = (
                reference.find(self.ns["tei"] + "monogr")
                .find(self.ns["tei"] + "imprint")
                .findall(self.ns["tei"] + "biblScope[@unit='page']")
            )
        elif reference.find(self.ns["tei"] + "analytic") is not None:
            page_list = (
                reference.find(self.ns["tei"] + "analytic")
                .find(self.ns["tei"] + "imprint")
                .findall(self.ns["tei"] + "biblScope[@unit='page']")
            )

        for page in page_list:
            if page is not None:
                for name, value in sorted(page.items()):
                    if name == "from":
                        page_string += value
                    if name == "to":
                        page_string += "--" + value
            else:
                page_string = "NA"

        return page_string

    def __get_reference_number_string(self, *, reference) -> str:
        number_string = ""

        if reference.find(self.ns["tei"] + "monogr") is not None:
            number_list = (
                reference.find(self.ns["tei"] + "monogr")
                .find(self.ns["tei"] + "imprint")
                .findall(self.ns["tei"] + "biblScope[@unit='issue']")
            )
        elif reference.find(self.ns["tei"] + "analytic") is not None:
            number_list = (
                reference.find(self.ns["tei"] + "analytic")
                .find(self.ns["tei"] + "imprint")
                .findall(self.ns["tei"] + "biblScope[@unit='issue']")
            )

        for number in number_list:
            if number is not None:
                number_string = number.text
            else:
                number_string = "NA"

        return number_string

    def __get_reference_volume_string(self, *, reference) -> str:
        volume_string = ""

        if reference.find(self.ns["tei"] + "monogr") is not None:
            volume_list = (
                reference.find(self.ns["tei"] + "monogr")
                .find(self.ns["tei"] + "imprint")
                .findall(self.ns["tei"] + "biblScope[@unit='volume']")
            )
        elif reference.find(self.ns["tei"] + "analytic") is not None:
            volume_list = (
                reference.find(self.ns["tei"] + "analytic")
                .find(self.ns["tei"] + "imprint")
                .findall(self.ns["tei"] + "biblScope[@unit='volume']")
            )

        for volume in volume_list:
            if volume is not None:
                volume_string = volume.text
            else:
                volume_string = "NA"

        return volume_string

    def __get_reference_journal_string(self, *, reference) -> str:
        journal_title = ""
        if reference.find(self.ns["tei"] + "monogr") is not None:
            journal_title = (
                reference.find(self.ns["tei"] + "monogr")
                .find(self.ns["tei"] + "title")
                .text
            )
        if journal_title is None:
            journal_title = ""
        return journal_title

    def __get_entrytype(self, *, reference) -> str:
        entrytype = "misc"
        if reference.find(self.ns["tei"] + "monogr") is not None:
            monogr_node = reference.find(self.ns["tei"] + "monogr")
            title_node = monogr_node.find(self.ns["tei"] + "title")
            if title_node is not None:
                if "j" == title_node.get("level", "NA"):
                    entrytype = "article"
                else:
                    entrytype = "book"
        return entrytype

    def get_bibliography(self):

        bibliographies = self.root.iter(self.ns["tei"] + "listBibl")
        tei_bib_db = []
        for bibliography in bibliographies:
            for reference in bibliography:
                try:
                    entrytype = self.__get_entrytype(reference=reference)
                    if "article" == entrytype:
                        ref_rec = {
                            "ID": self.__get_reference_bibliography_id(
                                reference=reference
                            ),
                            "ENTRYTYPE": entrytype,
                            "tei_id": self.__get_reference_bibliography_tei_id(
                                reference=reference
                            ),
                            "author": self.__get_reference_author_string(
                                reference=reference
                            ),
                            "title": self.__get_reference_title_string(
                                reference=reference
                            ),
                            "year": self.__get_reference_year_string(
                                reference=reference
                            ),
                            "journal": self.__get_reference_journal_string(
                                reference=reference
                            ),
                            "volume": self.__get_reference_volume_string(
                                reference=reference
                            ),
                            "number": self.__get_reference_number_string(
                                reference=reference
                            ),
                            "pages": self.__get_reference_page_string(
                                reference=reference
                            ),
                        }
                    elif "book" == entrytype:
                        ref_rec = {
                            "ID": self.__get_reference_bibliography_id(
                                reference=reference
                            ),
                            "ENTRYTYPE": entrytype,
                            "tei_id": self.__get_reference_bibliography_tei_id(
                                reference=reference
                            ),
                            "author": self.__get_reference_author_string(
                                reference=reference
                            ),
                            "title": self.__get_reference_title_string(
                                reference=reference
                            ),
                            "year": self.__get_reference_year_string(
                                reference=reference
                            ),
                        }
                    elif "misc" == entrytype:
                        ref_rec = {
                            "ID": self.__get_reference_bibliography_id(
                                reference=reference
                            ),
                            "ENTRYTYPE": entrytype,
                            "tei_id": self.__get_reference_bibliography_tei_id(
                                reference=reference
                            ),
                            "author": self.__get_reference_author_string(
                                reference=reference
                            ),
                            "title": self.__get_reference_title_string(
                                reference=reference
                            ),
                        }
                except etree.XMLSyntaxError:
                    continue

                ref_rec = {k: v for k, v in ref_rec.items() if v is not None}
                # print(ref_rec)
                tei_bib_db.append(ref_rec)

        return tei_bib_db

    def get_citations_per_section(self) -> dict:
        section_citations = {}
        sections = self.root.iter(self.ns["tei"] + "head")
        for section in sections:
            section_name = section.text
            if section_name is None:
                continue
            citation_nodes = section.getparent().iter(self.ns["tei"] + "ref")
            citations = [
                x.get("target", "NA").replace("#", "")
                for x in citation_nodes
                if "bibr" == x.get("type", "NA")
            ]
            citations = list(filter(lambda a: a != "NA", citations))
            if len(citations) > 0:
                section_citations[section_name.lower()] = citations
        return section_citations

    def mark_references(self, *, records):

        tei_records = self.get_bibliography()
        for record_dict in tei_records:
            if "title" not in record_dict:
                continue

            max_sim = 0.9
            max_sim_record = {}
            for local_record_dict in records:
                if local_record_dict["status"] not in [
                    colrev.record.RecordState.rev_included,
                    colrev.record.RecordState.rev_synthesized,
                ]:
                    continue
                rec_sim = colrev.record.Record.get_record_similarity(
                    record_a=colrev.record.Record(data=record_dict),
                    record_b=colrev.record.Record(data=local_record_dict),
                )
                if rec_sim > max_sim:
                    max_sim_record = local_record_dict
                    max_sim = rec_sim
            if len(max_sim_record) == 0:
                continue

            # Record found: mark in tei
            bibliography = self.root.find(".//" + self.ns["tei"] + "listBibl")
            # mark reference in bibliography
            for ref in bibliography:
                if ref.get(self.ns["w3"] + "id") == record_dict["tei_id"]:
                    ref.set("ID", max_sim_record["ID"])
            # mark reference in in-text citations
            for reference in self.root.iter(self.ns["tei"] + "ref"):
                if "target" in reference.keys():
                    if reference.get("target") == f"#{record_dict['tei_id']}":
                        reference.set("ID", max_sim_record["ID"])

            # if settings file available: dedupe_io match agains records

        if self.tei_path:
            tree = etree.ElementTree(self.root)
            tree.write(str(self.tei_path), pretty_print=True, encoding="utf-8")

        return self.root


if __name__ == "__main__":
    pass
