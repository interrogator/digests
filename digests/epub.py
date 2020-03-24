#!/usr/bin/python
# -*- coding: utf-8 -*-

import json
import os
import sys
import urllib
import xml.parsers.expat
import zipfile
from glob import glob

import html2text


def make_safe_name(name):
    safe_name = name.replace(" ", "-").lower()
    safe_name = "".join(i for i in safe_name if i.isalnum() or i in {"-", "_"}).lower()
    return safe_name


class ContainerParser:
    def __init__(self, xmlcontent=None):
        self.rootfile = ""
        self.xml = xmlcontent

    def startElement(self, name, attributes):
        if name == "rootfile":
            self.buffer = ""
            self.rootfile = attributes["full-path"]

    def parseContainer(self):
        parser = xml.parsers.expat.ParserCreate()
        parser.StartElementHandler = self.startElement
        parser.Parse(self.xml, 1)
        return self.rootfile


class BookParser:
    def __init__(self, xmlcontent=None):
        self.xml = xmlcontent
        self.title = ""
        self.author = ""
        self.inTitle = 0
        self.inAuthor = 0
        self.ncx = ""

    def startElement(self, name, attributes):
        if name == "dc:title":
            self.buffer = ""
            self.inTitle = 1
        elif name == "dc:creator":
            self.buffer = ""
            self.inAuthor = 1
        elif name == "item":
            if (
                attributes["id"] == "ncx"
                or attributes["id"] == "toc"
                or attributes["id"] == "ncxtoc"
            ):
                self.ncx = attributes["href"]

    def characters(self, data):
        if self.inTitle:
            self.buffer += data
        elif self.inAuthor:
            self.buffer += data

    def endElement(self, name):
        if name == "dc:title":
            self.inTitle = 0
            self.title = self.buffer
            self.buffer = ""
        elif name == "dc:creator":
            self.inAuthor = 0
            self.author = self.buffer
            self.buffer = ""

    def parseBook(self):
        parser = xml.parsers.expat.ParserCreate()
        parser.StartElementHandler = self.startElement
        parser.EndElementHandler = self.endElement
        parser.CharacterDataHandler = self.characters
        parser.Parse(self.xml, 1)
        # print('NC', self.ncx)
        return self.title, self.author, self.ncx


class NavPoint:
    def __init__(self, id=None, playorder=None, level=0, content=None, text=None, classy=None):
        self.id = id
        self.cls = classy
        self.content = content
        self.playorder = playorder
        self.level = level
        self.text = text


class TocParser:
    def __init__(self, xmlcontent=None):
        self.xml = xmlcontent
        self.currentNP = None
        self.stack = []
        self.inText = 0
        self.toc = []

    def startElement(self, name, attributes):
        if name == "navPoint":
            level = len(self.stack)
            self.currentNP = NavPoint(attributes["id"], attributes["playOrder"], level, classy=attributes.get("class"))
            self.stack.append(self.currentNP)
            self.toc.append(self.currentNP)
        elif name == "content":
            self.currentNP.content = urllib.parse.unquote(attributes["src"])
        elif name == "text":
            self.buffer = ""
            self.inText = 1

    def characters(self, data):
        if self.inText:
            self.buffer += data

    def endElement(self, name):
        if name == "navPoint":
            self.currentNP = self.stack.pop()
        elif name == "text":
            if self.inText and self.currentNP:
                self.currentNP.text = self.buffer
            self.inText = 0

    def parseToc(self):
        parser = xml.parsers.expat.ParserCreate()
        parser.StartElementHandler = self.startElement
        parser.EndElementHandler = self.endElement
        parser.CharacterDataHandler = self.characters
        parser.Parse(self.xml, 1)
        return self.toc


def make_meta_element(metadata):
    meta = "<meta "
    for k, v in metadata.items():
        v = f'"{v}"' if isinstance(v, str) else v  # repr?
        meta += f"{k.replace('_', '-')}={v} "
    return meta + "/>"


def post_process(text):
    out = []
    header = False
    lines = text.splitlines()
    for line in lines:
        if "<meta header=true" in line:
            header = True
            out.append("\n" + line)
            continue
        if header:
            if "</meta" in line:
                header = False
            out[-1] += line
        else:
            out.append(line)

    return '\n'.join(out)


def convert(epub, metafile=None):

    text_meta = dict()
    if metafile:
        with open(metafile, "r") as fo:
            text_meta = json.loads(fo.read())

    print("Processing %s ..." % epub)
    # open zip
    file = zipfile.ZipFile(epub, "r")
    # get root
    rootfile = ContainerParser(file.read("META-INF/container.xml")).parseContainer()
    # get main metadata
    title, author, ncx = BookParser(file.read(rootfile)).parseBook()

    meta = dict(book_title=title, author=author)

    # what is this?
    ops = "/".join(rootfile.split("/")[:-1])
    if ops:
        ops = ops + "/"

    # get list of components
    toc = TocParser(file.read(ops + ncx)).parseToc()

    # make corpus directory
    safe_title = make_safe_name(title)
    if metafile and safe_title in text_meta:
        meta.update(text_meta[safe_title])
    outdir = os.path.join('out', safe_title)
    os.makedirs(outdir)

    # hold data in here
    part_paths = []

    html_parser = html2text.HTML2Text()
    html_parser.body_width = 0  # no shitty wrapping
    html_parser.ignore_images = True
    html_parser.ignore_links = True
    chapter_number = 0
    part_number = 0
    part_paths = []

    not_chapters = {"copyright", "cover", "cover-page", "contents", "editor's note", "editors' note", "editor’s note", title.lower()}

    is_part = {"epub3_p", "epub_p"}
    is_chapter = {"epub_c", "epub3_c", "-h-", "index_split_"}

    has_no_chapters = True
    for t in toc:
        if not t.level:
            continue
        if t.content.startswith("ch") or any(i in t.content for i in is_chapter):
            has_no_chapters = False
            break

    # iterate over components
    for t in toc:
        # print("ID", t.level, t.cls, t.content, t.id)
        # make folder for each part
        if t.content.startswith("part") or any(i in t.content for i in is_part) and "epub_prl" not in t.content:
            part_number += 1
            part_name = t.text.strip()
            numfilled = str(part_number).zfill(3)
            safe_name = make_safe_name(part_name)
            part_path = f"{numfilled}-{safe_name}"
            part_path = os.path.join(outdir, part_path)
            os.makedirs(part_path)
            meta.update(dict(part_name=part_name, part_number=part_number))
            part_paths.append(part_path)
        # make file containing chapter
        if t.content.startswith("ch") or any(i in t.content for i in is_chapter) or has_no_chapters or t.cls == "chapter":
            chapter_name = t.text.strip().strip('.')
            if chapter_name.lower() in not_chapters:
                continue
            chapter_number += 1
            numfilled = str(chapter_number).zfill(3)
            safe_name = make_safe_name(chapter_name)
            if safe_name in {
                "cover-page",
                "other-books-by-this-author",
                "title-page",
                "dedication",
                "about",
                "map",
                "epigraph",
                "acknowledgements",
                "about-the-author"
            }:
                continue
            meta.update(dict(chapter_name=chapter_name, chapter_number=chapter_number))
            meta_string = make_meta_element(meta)
            chapter_path = f"{numfilled}-{safe_name}"
            if part_paths:
                chapter_path = os.path.join(part_paths[-1], chapter_path + ".txt")
            else:
                chapter_path = os.path.join(outdir, chapter_path + ".txt")

            html = file.read(ops + t.content.split("#")[0])
            # todo: split out the chapter title, or no
            text = html_parser.handle(html.decode("utf-8"))

            text = post_process(text)
            # print('TEXT', text[:1000])

            with open(chapter_path, "w") as fo:
                fo.write(meta_string + "\n")
                fo.write(text + "\n")


if __name__ == "__main__":
    filenames = glob(sys.argv[-1])
    metafile = sys.argv[1]
    metafile = metafile if metafile != "none" else None
    for filename in filenames:
        convert(filename, metafile)
