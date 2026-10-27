# -*- coding: utf-8 -*-
"""Build the self-contained page from v2_page.json + v2_template.html."""
import os, json

HERE = os.path.dirname(os.path.abspath(__file__))


def build(out_path=None):
    with open(os.path.join(HERE, 'v2_page.json'), encoding='utf-8') as f:
        data = json.load(f)
    with open(os.path.join(HERE, 'v2_template.html'), encoding='utf-8') as f:
        tpl = f.read()

    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    html = tpl.replace('__V2_DATA__', payload)
    out = out_path or os.path.join(HERE, 'review_v2.html')
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print('wrote', out, '%.1f KB' % (os.path.getsize(out) / 1024))
    return out


if __name__ == '__main__':
    build(os.path.join(HERE, 'review_v2.html'))
