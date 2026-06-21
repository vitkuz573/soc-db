"""Extract first 3 wikitables from given Wikipedia pages."""

import re
import sys
from bs4 import BeautifulSoup, Tag

sys.path.insert(0, str(__file__).rsplit("/", 2)[0] + "/scripts")
from common import fetch


def find_heading(table):
    """Find the nearest h2/h3/h4 heading before the table."""
    for prev in table.find_all_previous(["h2", "h3", "h4"]):
        txt = prev.get_text(strip=True)
        if txt:
            # strip the "[edit]" part
            txt = re.sub(r"\[.*?\]", "", txt).strip()
            return txt
    return "(no heading)"


def extract_cells(row):
    """Extract all cell texts from a tr, returning cleaned strings."""
    return [clean(td.get_text(" ", strip=True)) for td in row.find_all(["th", "td"])]


def clean(text):
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[\w+\]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def get_page_name(url):
    return url.rstrip("/").split("/")[-1].replace("_", " ")


def fmt_cell(c):
    if c is None:
        return "—"
    c = str(c)
    if len(c) > 80:
        c = c[:77] + "..."
    return c


def process_table(table, index):
    heading = find_heading(table)

    # get all headers from thead or first tr
    headers = []
    thead = table.find("thead")
    if thead:
        rows = thead.find_all("tr")
        for row in rows:
            for th in row.find_all("th"):
                headers.append(clean(th.get_text(" ", strip=True)))
    else:
        first_tr = table.find("tr")
        if first_tr:
            for th in first_tr.find_all("th"):
                headers.append(clean(th.get_text(" ", strip=True)))

    # get data rows
    tbody = table.find("tbody")
    if tbody:
        data_rows = tbody.find_all("tr")
    else:
        data_rows = table.find_all("tr")

    # skip header row if we got headers from first tr already
    if not thead and headers:
        data_rows = data_rows[1:] if data_rows else []

    # filter out rows with only th (sub-headers)
    rows_data = []
    for row in data_rows:
        cells = row.find_all("td")
        if not cells:
            continue
        # skip rows that are entirely th
        if all(t.name == "th" for t in row.find_all(["th", "td"])):
            continue
        rows_data.append([clean(c.get_text(" ", strip=True)) for c in cells])

    return {
        "heading": heading,
        "headers": headers,
        "rows": rows_data,
    }


def process_page(url, max_tables=3):
    page_name = get_page_name(url)
    print(f"\nPAGE: {page_name}")
    print(f"  URL: {url}")

    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")

    # find all wikitables
    tables = soup.find_all("table", class_=re.compile(r"wikitable"))
    if not tables:
        print("  No wikitables found.")
        return

    count = 0
    for i, table in enumerate(tables):
        if count >= max_tables:
            break

        result = process_table(table, count + 1)
        if not result["rows"]:
            continue

        count += 1
        heading = result["heading"]
        headers = result["headers"]
        rows = result["rows"]

        print(f"  TABLE {count} (heading: \"{heading}\"):")
        hdr_str = ", ".join(f"\"{h}\"" for h in headers) if headers else "(no header row)"
        print(f"    Headers: [{hdr_str}]")

        for ri, row in enumerate(rows):
            if ri >= 5:
                break
            c1 = fmt_cell(row[0]) if len(row) > 0 else "—"
            c2 = fmt_cell(row[1]) if len(row) > 1 else "—"
            print(f"    Row {ri + 1}: {c1} | {c2}")

        if len(rows) > 5:
            print(f"    ... ({len(rows) - 5} more rows)")


def find_intel_atom_tables(url):
    """Special handling for Intel Atom page."""
    page_name = get_page_name(url)
    print(f"\nPAGE: {page_name}")
    print(f"  URL: {url}")

    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table", class_=re.compile(r"wikitable"))

    if not tables:
        print("  No wikitables found.")
        return

    # first table
    print("  TABLE 1 (heading: \"{}\"):".format(process_table(tables[0], 1)["heading"]))
    result1 = process_table(tables[0], 1)
    hdr_str = ", ".join(f"\"{h}\"" for h in result1["headers"]) if result1["headers"] else "(no header row)"
    print(f"    Headers: [{hdr_str}]")
    for ri, row in enumerate(result1["rows"]):
        if ri >= 5:
            break
        c1 = fmt_cell(row[0]) if len(row) > 0 else "—"
        c2 = fmt_cell(row[1]) if len(row) > 1 else "—"
        print(f"    Row {ri + 1}: {c1} | {c2}")
    if len(result1["rows"]) > 5:
        print(f"    ... ({len(result1['rows']) - 5} more rows)")

    # find table with most columns
    max_cols = 0
    max_table = None
    max_idx = -1
    for i, table in enumerate(tables):
        cols = len(table.find_all("th")) + len(table.find_all("td"))
        if cols > max_cols:
            max_cols = cols
            max_table = table
            max_idx = i

    if max_table is not None and max_idx > 0:
        print(f"\n  TABLE with most columns (table #{max_idx + 1}, heading: \"{process_table(max_table, max_idx + 1)['heading']}\"):")
        result_max = process_table(max_table, max_idx + 1)
        hdr_str = ", ".join(f"\"{h}\"" for h in result_max["headers"]) if result_max["headers"] else "(no header row)"
        print(f"    Headers: [{hdr_str}]")
        for ri, row in enumerate(result_max["rows"]):
            if ri >= 5:
                break
            c1 = fmt_cell(row[0]) if len(row) > 0 else "—"
            c2 = fmt_cell(row[1]) if len(row) > 1 else "—"
            print(f"    Row {ri + 1}: {c1} | {c2}")
        if len(result_max["rows"]) > 5:
            print(f"    ... ({len(result_max['rows']) - 5} more rows)")


if __name__ == "__main__":
    urls = [
        "https://en.wikipedia.org/wiki/Tegra",
        "https://en.wikipedia.org/wiki/Broadcom",
        "https://en.wikipedia.org/wiki/Marvell_Technology_Group",
        "https://en.wikipedia.org/wiki/OMAP",
        "https://en.wikipedia.org/wiki/Rockchip",
        "https://en.wikipedia.org/wiki/Allwinner_Technology",
        "https://en.wikipedia.org/wiki/Amlogic",
        "https://en.wikipedia.org/wiki/NXP_i.MX",
        "https://en.wikipedia.org/wiki/Ingenic",
    ]

    for url in urls:
        process_page(url, max_tables=3)

    find_intel_atom_tables("https://en.wikipedia.org/wiki/List_of_Intel_Atom_processors")
