"""Render registry/index.tsv from the parsed apps.yaml (official tools only).

Format: tab-separated, LF line endings, one header line, then one line per
official tool in apps.yaml order:

    #name<TAB>repo<TAB>commit<TAB>kind

name = entry name, repo = the entry's repo (github.com/owner/name),
commit = the pinned 40-hex commit (version), kind = the entry's pattern.
"""

HEADER = "#name\trepo\tcommit\tkind\n"


def render(data) -> str:
    out = [HEADER]
    for app in (data.get("apps", {}).get("official") or []):
        fields = [str(app.get(k, "")) for k in ("name", "repo", "version", "pattern")]
        out.append("\t".join(fields) + "\n")
    return "".join(out)
