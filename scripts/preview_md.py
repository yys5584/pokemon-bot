"""Simple Markdown preview server."""
import http.server
import os

PORT = 8091
MD_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "camp_system_spec.md")

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>배틀 상성 &amp; 레어리티 개편 기획서</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 900px; margin: 0 auto; padding: 20px 40px; background: #0d1117; color: #c9d1d9; line-height: 1.6; }
  h1 { color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 10px; }
  h2 { color: #58a6ff; border-bottom: 1px solid #21262d; padding-bottom: 6px; margin-top: 32px; }
  h3 { color: #d2a8ff; }
  table { border-collapse: collapse; width: 100%%; margin: 12px 0; }
  th, td { border: 1px solid #30363d; padding: 8px 12px; text-align: left; }
  th { background: #161b22; color: #58a6ff; }
  tr:nth-child(even) { background: #161b22; }
  code { background: #161b22; padding: 2px 6px; border-radius: 4px; color: #e6edf3; font-size: 0.9em; }
  pre { background: #161b22; padding: 16px; border-radius: 8px; overflow-x: auto; border: 1px solid #30363d; }
  pre code { padding: 0; background: none; }
  hr { border: none; border-top: 1px solid #30363d; margin: 24px 0; }
  strong { color: #e6edf3; }
  ul, ol { padding-left: 24px; }
  li { margin: 4px 0; }
  a { color: #58a6ff; }
</style>
</head>
<body>
%%CONTENT%%
</body>
</html>
"""

def md_to_html(md: str) -> str:
    """Minimal markdown to HTML converter."""
    import re
    lines = md.split('\n')
    html_lines = []
    in_table = False
    in_code = False
    code_buf = []
    in_ul = False

    i = 0
    while i < len(lines):
        line = lines[i]

        # Code blocks
        if line.strip().startswith('```'):
            if in_code:
                html_lines.append('<code>' + escape('\n'.join(code_buf)) + '</code></pre>')
                code_buf = []
                in_code = False
            else:
                lang = line.strip()[3:]
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue

        # Close ul if needed
        if in_ul and not line.strip().startswith('- '):
            html_lines.append('</ul>')
            in_ul = False

        # Empty line
        if not line.strip():
            if in_table:
                in_table = False
            html_lines.append('')
            i += 1
            continue

        # Headings
        m = re.match(r'^(#{1,4})\s+(.*)', line)
        if m:
            level = len(m.group(1))
            html_lines.append(f'<h{level}>{inline(m.group(2))}</h{level}>')
            i += 1
            continue

        # HR
        if line.strip() == '---':
            html_lines.append('<hr>')
            i += 1
            continue

        # Table
        if '|' in line and line.strip().startswith('|'):
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            # Check if next line is separator
            if i + 1 < len(lines) and re.match(r'^[\s|:-]+$', lines[i+1]):
                # Header row
                html_lines.append('<table><thead><tr>' +
                    ''.join(f'<th>{inline(c)}</th>' for c in cells) +
                    '</tr></thead><tbody>')
                in_table = True
                i += 2  # skip separator
                continue
            elif in_table:
                html_lines.append('<tr>' +
                    ''.join(f'<td>{inline(c)}</td>' for c in cells) +
                    '</tr>')
                # Check if next line is not a table
                if i + 1 >= len(lines) or not lines[i+1].strip().startswith('|'):
                    html_lines.append('</tbody></table>')
                    in_table = False
                i += 1
                continue

        # Unordered list
        m = re.match(r'^(\s*)[-*]\s+(.*)', line)
        if m:
            if not in_ul:
                html_lines.append('<ul>')
                in_ul = True
            html_lines.append(f'<li>{inline(m.group(2))}</li>')
            i += 1
            continue

        # Paragraph
        html_lines.append(f'<p>{inline(line)}</p>')
        i += 1

    if in_ul:
        html_lines.append('</ul>')
    if in_table:
        html_lines.append('</tbody></table>')

    return '\n'.join(html_lines)


def escape(s: str) -> str:
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def inline(s: str) -> str:
    import re
    s = s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'`(.+?)`', r'<code>\1</code>', s)
    return s


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        with open(MD_PATH, 'r', encoding='utf-8') as f:
            md = f.read()
        content = md_to_html(md)
        html = HTML_TEMPLATE.replace('%%CONTENT%%', content)
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def log_message(self, format, *args):
        print(f"[MD Preview] {args[0]}")


if __name__ == '__main__':
    server = http.server.HTTPServer(('0.0.0.0', PORT), Handler)
    print(f"[MD Preview] http://localhost:{PORT}")
    server.serve_forever()
