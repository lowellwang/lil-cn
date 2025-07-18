import re
import html
import json
import os
from bs4 import BeautifulSoup
from graphviz import Digraph

def parse_links_from_text(text):
    """
    从解码后的文本中提取 Twine 跳转链接目标（去除空格）。
    支持 [[label -> target]] 和 [[target]] 两种格式。
    """
    dec = html.unescape(text)
    # 箭头链接
    arrow_pattern = re.compile(r'\[\[\s*.*?-\s*(?:>|&gt;)\s*(.*?)\s*\]\]')
    raw_links = arrow_pattern.findall(dec)
    clean_links = [dst.replace(' ', '') for dst in raw_links]
    # 简单链接
    inside = re.findall(r'\[\[\s*([^]]+?)\s*\]\]', dec)
    simple = [it for it in inside if '->' not in it and '|' not in it]
    simple_links = [it.replace(' ', '') for it in simple]
    return sorted(set(clean_links + simple_links))


def parse_html(file_path):
    """
    解析 HTML 文件，返回 dict[name] = {macros, macros_count, links}。
    """
    soup = BeautifulSoup(open(file_path, encoding='utf-8'), 'html.parser')
    passages = {}
    for tag in soup.find_all('tw-passagedata'):
        name = html.unescape(tag.get('name')).replace(' ', '')
        text = html.unescape(tag.get_text()).replace(' ', '')
        # 宏
        macros = re.findall(r'\(\s*([A-Za-z0-9_]+)\s*:', text)
        # 链接
        links = parse_links_from_text(text)
        passages[name] = {
            'macros': sorted(set(macros)),
            'macros_count': len(macros),
            'links': links
        }
    return passages


def load_translation_passages(json_path):
    """
    从 JSON 翻译文件加载，每项为 {name: text}，返回 dict[name] = {macros, macros_count, links}。
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    trans = {}
    for raw_name, raw_text in data.items():
        name = html.unescape(raw_name).replace(' ', '')
        text = html.unescape(raw_text).replace(' ', '')
        macros = re.findall(r'\(\s*([A-Za-z0-9_]+)\s*:', text)
        links = parse_links_from_text(text)
        trans[name] = {
            'macros': sorted(set(macros)),
            'macros_count': len(macros),
            'links': links
        }
    return trans


def compare_passages(html_passages, json_passages):
    """
    比较 HTML 和 JSON 中每个 name 的宏及链接和宏数量：
      - 都存在且宏列表、宏数量、链接一致: pass
      - 都存在但存在差异: mismatch + 详情
      - HTML 有而 JSON 没有: 未翻译
      - JSON 有而 HTML 没有: 错误
    返回 report dict。
    """
    report = {}
    all_names = set(html_passages) | set(json_passages)
    for name in sorted(all_names):
        in_html = name in html_passages
        in_json = name in json_passages
        if in_html and in_json:
            h = html_passages[name]
            j = json_passages[name]
            macros_set_match = set(h['macros']) == set(j['macros'])
            macros_count_match = h['macros_count'] == j['macros_count']
            links_match = set(h['links']) == set(j['links'])
            if macros_set_match and macros_count_match and links_match:
                report[name] = {'status': 'pass'}
            else:
                entry = {'status': 'mismatch'}
                if not macros_set_match:
                    entry['html_macros'] = h['macros']
                    entry['json_macros'] = j['macros']
                if not macros_count_match:
                    entry['html_macros_count'] = h['macros_count']
                    entry['json_macros_count'] = j['macros_count']
                if not links_match:
                    entry['html_links'] = h['links']
                    entry['json_links'] = j['links']
                report[name] = entry
        elif in_html:
            report[name] = {'status': '未翻译'}
        else:
            report[name] = {'status': '错误'}
    return report


def write_json(data, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'Written JSON to {path}')


def generate_flowchart(passages, output_prefix='flowchart'):
    connected = set()
    for src, data in passages.items():
        if data['links']:
            connected.add(src)
            for dst in data['links']:
                connected.add(dst)
    dot = Digraph(comment='Twine Story Flow', format='png')
    for name in connected:
        dot.node(name, name)
    for src, data in passages.items():
        for dst in data['links']:
            if src in connected and dst in connected:
                dot.edge(src, dst)
    dot.render(output_prefix, view=True)
    print(f'Flowchart saved as {output_prefix}.png')


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Analyze and compare Twine Harlowe passages')
    parser.add_argument('html', help='原始 HTML 文件路径')
    parser.add_argument('--json', help='翻译 JSON 文件路径')
    parser.add_argument('--report', default='compare_report.json', help='对比报告输出路径')
    parser.add_argument('--flow', default='flowchart', help='流程图输出前缀')
    args = parser.parse_args()

    html_passages = parse_html(args.html)
    write_json(html_passages, 'html_passages.json')
    print('Saved HTML passages to html_passages.json')

    if args.json:
        json_passages = load_translation_passages(args.json)
        report = compare_passages(html_passages, json_passages)
        write_json(report, args.report)
        print(f'Report saved to {args.report}')

    # generate_flowchart(html_passages, args.flow)

if __name__ == '__main__':
    main()
