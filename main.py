#!/usr/bin/env python

import os
import urllib.request
import re
import sqlite3
import urllib.parse

from bs4 import BeautifulSoup
from slugify import slugify


DOMAIN = "https://love2d.org"
RESOURCESPATH = "love2d.docset/Contents/Resources"
DOCPATH = "love2d.docset/Contents/Resources/Documents"
RESTRICTED_EXTENSIONS = ["png", "jpg", "jpeg", "php"]

class DashLoveParser:
    def __init__(self):
        self.css_is_downloaded = False

        self.init_database()
        self.parse_pages("Callback", "https://love2d.org/wiki/Category:Callbacks")
        self.parse_pages("Enum", "https://love2d.org/w/index.php?title=Special:Ask&offset=0&limit=500&q=%5B%5BCategory%3AEnums%5D%5D&p=headers%3Dhide%2Fformat%3Dbroadtable&po=%3FDescription%0A")
        self.parse_pages("Function", "https://love2d.org/w/index.php?title=Special:Ask&offset=0&limit=500&q=%5B%5BCategory%3AFunctions%5D%5D&p=headers%3Dhide%2Fformat%3Dbroadtable&po=%3FDescription%0A")
        self.parse_pages("Module", "https://love2d.org/w/index.php?title=Special:Ask&offset=0&limit=500&q=%5B%5BCategory%3AModules%5D%5D&p=headers%3Dhide%2Fformat%3Dbroadtable&po=%3FDescription%0A")
        self.parse_pages("Type", "https://love2d.org/w/index.php?title=Special:Ask&offset=0&limit=500&q=%5B%5BCategory%3ATypes%5D%5D&p=headers%3Dhide%2Fformat%3Dbroadtable&po=%3FDescription%0A")
        self.clean_links()

    def parse_pages(self, entry_type, url):
        """Parse pages for a type and save them locally."""
        links = []

        # While since the last page has been reached
        while True:
            html = urllib.request.urlopen(url).read()
            document = BeautifulSoup(html, "html.parser")

            table = document.find("table", class_="smwtable")
            columns = [row for row in table.find_all("td", class_="smwtype_wpg")]

            # Search english links
            for column in columns:
                link = column.find("a")

                if not link["href"].endswith(")"):
                    links.append(link)

            # Search if it is the last page
            next_page = document.find("a", text="Next")

            # The link is not found
            if next_page is None:
                break

            url = "%s/%s" % (DOMAIN, next_page["href"])

        for link in links:
            # Create the filename based on the last part of the url
            page_filename = "%s.html" % self.slugify(link["href"].split("/")[-1])

            html = urllib.request.urlopen("%s/%s" % (DOMAIN, link["href"])).read()
            document = BeautifulSoup(html, "html.parser")

            if self.css_is_downloaded is False:
                # Download the css
                css_link = document.find("link", attrs={"rel": "stylesheet"})["href"]
                css_content = urllib.request.urlopen(css_link).read()

                with open("%s/main.css" % DOCPATH, "wb") as css_file:
                    css_file.write(css_content)

                self.css_is_downloaded = True

            processed_page_html = self.process_page(document)
            processed_page_html = self.download_medias(processed_page_html)

            # Save the page in the docset documents folder
            with open("%s/%s" % (DOCPATH, page_filename), "w") as document_file:
                document_file.write(processed_page_html)

            self.insert_entry(document.h1.text, entry_type, page_filename)

    def download_medias(self, html):
        """Downloads medias of the page."""
        document = BeautifulSoup(html, "html.parser")

        for media in document.find_all("img"):
            src = media["src"]
            media["src"] = self.slugify(src, is_filename=True)

            # Don't download existing files
            if os.path.exists("%s/%s" % (DOCPATH, media["src"])):
                continue

            with open("%s/%s" % (DOCPATH, media["src"]), "wb") as media_file:
                media_file.write(urllib.request.urlopen("https://love2d.org/%s" % src).read())

        return str(document)

    def process_page(self, document):
        """Returns the body content of the page."""
        # Remove the footer part
        try:
            document.find("div", attrs={"class": "printfooter"}).extract()
            document.find("div", attrs={"class": "catlinks"}).extract()
        except AttributeError:
            pass

        try:
            languages = document.find("div", class_="i18n")
        except AttributeError:
            languages = None

        if languages != None:
            try:
                languages.find_previous_sibling("h2").extract()
            except AttributeError:
                pass
            finally:
                languages.extract()

        # Find the title of the page and its content
        title = document.find("h1", attrs={"id": "firstHeading"})
        content = document.find("div", attrs={"id": "bodyContent"})

        # Create a body for the page
        html = """
    <!DOCTYPE html>
    <html lang="en">
        <head>
            <title>%s</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <link href="main.css" rel="stylesheet">
        </head>
        <body>
            %s
        </body>
    </html>
        """

        # Add the title and the content in the html
        html = html % ("%s - LOVE" % title.text, str(title) + str(content))

        page = BeautifulSoup(html, "html.parser")

        # Find all links and slugify the href
        all_links = page.find_all("a")

        # Remove links that are not part of the documentation
        links = []

        for link in all_links:
            # Extract links that haven't the href attribute
            if not link.has_attr("href"):
                link.replaceWithChildren()
                continue

            href = link["href"]
            extension = urllib.parse.urlparse(href).path.split(".")[-1]

            if re.match(r"\d+\.\d+\.\d+", href.split("/")[-1]):
                link.replaceWithChildren()
            elif not href.startswith("/wiki") or extension in RESTRICTED_EXTENSIONS:
                link.replaceWithChildren()
            elif "(" in href or ")" in href:
                link.replaceWithChildren()
            else:
                links.append(href)

        links = list(set(links))

        # TODO: Change the multiple bs4 instanciation
        html = str(page)

        for link in links:
            # Remove the wiki part in the href
            href = link.replace("/wiki/", "")
            html = html.replace('href="%s"' % link, 'href="%s.html"' % self.slugify(href))

        return html

    def clean_links(self):
        """Remove pages links that not belong to the documentation."""
        files = [file for file in os.listdir(DOCPATH) if file.endswith(".html")]

        for page_filename in files:
            with open("%s/%s" % (DOCPATH, page_filename)) as document_file:
                html = document_file.read()

            document = BeautifulSoup(html, "html.parser")

            # Remove also links
            try:
                see_also_h2 = document.find("span", id=re.compile("See_Also", re.I)).parent
            except AttributeError:
                see_also_h2 = None

            if not see_also_h2 is None:
                see_also_ul = see_also_h2.find_next_sibling("ul")

                for link in see_also_ul.find_all("a"):
                    filename = self.slugify(link["href"], is_filename=True)

                    if not os.path.exists("%s/%s" % (DOCPATH, filename)):
                        link.decompose()

                # Remove the also links title if there is no more link
                if len(see_also_ul.find_all("li")) == 0:
                    see_also_h2.decompose()
                    see_also_ul.decompose()

            # Remove links that not belong to the documentation
            for link in document.find_all("a"):
                filename = self.slugify(link["href"], is_filename=True)

                if not os.path.exists("%s/%s" % (DOCPATH, filename)):
                    link.replaceWithChildren()

            with open("%s/%s" % (DOCPATH, page_filename), "w") as document_file:
                document_file.write(str(document))

    def init_database(self):
        """
        Init the database by creating the table and
        dropping it when starting the script.

        Returns the current cursor.
        """
        # Create the sqlite3 database
        self.conn = sqlite3.connect("%s/docSet.dsidx" % RESOURCESPATH)
        self.cur = self.conn.cursor()

        # Drop the database
        self.cur.execute('DROP TABLE searchIndex;')

        # Create the table and its index
        self.cur.execute('CREATE TABLE searchIndex(id INTEGER PRIMARY KEY, name TEXT, type TEXT, path TEXT);')
        self.cur.execute('CREATE UNIQUE INDEX anchor ON searchIndex (name, type, path);')

    def insert_entry(self, name, entry_type, path):
        """Insert in database the entry."""
        self.cur.execute("INSERT OR IGNORE INTO searchIndex(name, type, path) VALUES (?, ?, ?)", (name, entry_type, path))
        self.conn.commit()

        print("name: \033[92m%s\033[0m, type: \033[92m%s\033[0m, path: \033[92m%s\033[0m" % (name, entry_type, path))

    def slugify(self, text, is_filename=False):
        """Slugify a text."""
        if is_filename:
            filename, extension = text.rsplit(".", 1)

            return "%s.%s" % (slugify(filename, to_lower=True), extension)

        return slugify(text, to_lower=True)


if __name__ == '__main__':
    DashLoveParser()
