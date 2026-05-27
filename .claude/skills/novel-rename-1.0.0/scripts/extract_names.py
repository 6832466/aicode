#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小说推文人物改名 - 角色名称提取脚本
扫描全文，提取所有疑似角色名称，输出供用户确认
"""

import sys
import os
import re
import json
import argparse


def read_file(filepath):
    """读取文件，自动尝试UTF-8和GBK编码"""
    for encoding in ['utf-8', 'gbk', 'gb2312', 'utf-8-sig']:
        try:
            with open(filepath, 'r', encoding=encoding) as f:
                content = f.read()
            return content, encoding
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"无法识别文件编码: {filepath}")


def extract_chinese_names(text):
    """提取文中疑似中文人名"""
    names = {}

    common_surnames = [
        '赵', '钱', '孙', '李', '周', '吴', '郑', '王', '冯', '陈',
        '褚', '卫', '蒋', '沈', '韩', '杨', '朱', '秦', '尤', '许',
        '何', '吕', '施', '张', '孔', '曹', '严', '华', '金', '魏',
        '陶', '姜', '戚', '谢', '邹', '喻', '柏', '水', '窦', '章',
        '云', '苏', '潘', '葛', '奚', '范', '彭', '郎', '鲁', '韦',
        '昌', '马', '苗', '凤', '花', '方', '俞', '任', '袁', '柳',
        '酆', '鲍', '史', '唐', '费', '廉', '岑', '薛', '雷', '贺',
        '倪', '汤', '滕', '殷', '罗', '毕', '郝', '邬', '安', '常',
        '乐', '于', '时', '傅', '皮', '卞', '齐', '康', '伍', '余',
        '元', '卜', '顾', '孟', '平', '黄', '和', '穆', '萧', '尹',
        '欧阳', '司马', '上官', '诸葛', '慕容', '公孙', '东方', '令狐',
    ]

    prefix_titles = ['老', '小', '阿']
    suffix_titles = ['总', '哥', '姐', '弟', '妹', '叔', '伯', '婶', '爷',
                     '婆', '公', '妈', '爸', '娘', '师傅', '老师', '老板',
                     '先生', '女士', '夫人', '太太', '小姐', '大人', '公子',
                     '姑娘', '少爷', '掌门', '长老', '师兄', '师弟',
                     '师姐', '师妹', '道友', '仙子', '真人', '大师']

    for surname in common_surnames:
        pattern = rf'(?<=[，。！？、；：""''\s\n\r])({surname}[一-龥]{{1,2}})(?=[，。！？、；：""''\s\n\r])'
        matches = re.findall(pattern, text)
        for m in matches:
            if m not in names:
                names[m] = 0
            names[m] += 1

        for prefix in prefix_titles:
            call = prefix + surname
            count = text.count(call)
            if count > 0:
                if call not in names:
                    names[call] = 0
                names[call] += count

    for title in suffix_titles:
        pattern = rf'([一-龥]{{1,3}}){re.escape(title)}'
        matches = re.findall(pattern, text)
        for m in matches:
            full = m + title
            if full not in names:
                names[full] = 0
            names[full] += 1

    sorted_names = sorted(names.items(), key=lambda x: x[1], reverse=True)
    return sorted_names


def analyze_name_relations(names_list):
    """分析名字之间的逻辑关系"""
    relations = []
    surnames = {}

    for name, count in names_list:
        if len(name) >= 2:
            surname = name[0]
            if surname not in surnames:
                surnames[surname] = []
            surnames[surname].append((name, count))

    for surname, members in surnames.items():
        if len(members) >= 2:
            member_names = [m[0] for m in members]
            relations.append({
                "type": "同姓（疑似家族/同门）",
                "members": member_names,
                "note": "改名时应保持同姓"
            })

    return relations


def main():
    parser = argparse.ArgumentParser(description='小说推文人物改名 - 角色名称提取')
    parser.add_argument('input', help='输入文件路径')
    parser.add_argument('-o', '--output', help='输出JSON信息文件路径（可选，默认输出到控制台）')
    parser.add_argument('-t', '--threshold', type=int, default=2, help='最少出现次数过滤（默认2次）')
    args = parser.parse_args()

    content, encoding = read_file(args.input)
    total_chars = len(content)

    names_list = extract_chinese_names(content)
    filtered = [(n, c) for n, c in names_list if c >= args.threshold]
    relations = analyze_name_relations(filtered)

    result = {
        "source_file": os.path.abspath(args.input),
        "encoding": encoding,
        "total_chars": total_chars,
        "detected_names": [
            {"name": n, "count": c} for n, c in filtered
        ],
        "name_relations": relations,
        "note": "请确认以上角色名是否正确，并指定新名字。关系列出的角色改名时需保持逻辑一致。新名字不能是明星/公众人物的名字。"
    }

    output_json = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output_json)
        print(f"角色信息已保存到: {args.output}")
    else:
        print(output_json)

    print(f"\n总结: 检测到 {len(filtered)} 个疑似角色名, {len(relations)} 组逻辑关系")


if __name__ == '__main__':
    main()
