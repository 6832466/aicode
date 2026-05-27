#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小说推文错别字修正 - 合并输出脚本
将分段修正后的文本块合并为完整文件，并生成修改清单
"""

import sys
import os
import json
import argparse
from datetime import datetime


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


def detect_newline_type(text):
    """检测换行符类型"""
    if '\r\n' in text:
        return '\r\n'  # CRLF (Windows)
    elif '\n' in text:
        return '\n'    # LF (Unix)
    else:
        return '\n'    # 默认


def generate_output_path(input_path, suffix):
    """生成输出文件路径"""
    base, ext = os.path.splitext(input_path)
    return f"{base}{suffix}{ext}"


def format_changes_list(changes, source_file, total_chars):
    """格式化修改清单"""
    lines = [
        "=== 错别字修正清单 ===",
        f"源文件：{source_file}",
        f"修正时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"总字数：{total_chars}",
        f"修正数量：{sum(len(v) for v in changes.values())}处",
        "",
        "--- 修改明细 ---",
        ""
    ]
    
    for chunk_name, chunk_changes in changes.items():
        if not chunk_changes:
            lines.append(f"{chunk_name}：本段无错别字")
        else:
            lines.append(f"{chunk_name}：")
            for change in chunk_changes:
                lines.append(f"  [{change['original']}] → [{change['fixed']}]")
        lines.append("")
    
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='小说推文错别字修正 - 合并输出')
    parser.add_argument('-i', '--input', required=True, help='原始文件路径')
    parser.add_argument('-c', '--chunks-dir', required=True, help='分段修正文件所在目录')
    parser.add_argument('-n', '--chunk-count', type=int, required=True, help='分段数量')
    parser.add_argument('--changes', help='修改清单JSON文件路径（可选）')
    parser.add_argument('--encoding', default='utf-8', help='输出文件编码（默认utf-8）')
    args = parser.parse_args()
    
    # 读取原始文件获取换行符类型
    original_content, _ = read_file(args.input)
    newline = detect_newline_type(original_content)
    total_chars = len(original_content)
    
    # 合并所有分段修正文件
    merged_chunks = []
    for i in range(1, args.chunk_count + 1):
        chunk_file = os.path.join(args.chunks_dir, f"chunk_{i:04d}.txt")
        if not os.path.exists(chunk_file):
            print(f"警告: 分段文件不存在: {chunk_file}", file=sys.stderr)
            continue
        chunk_content, _ = read_file(chunk_file)
        merged_chunks.append(chunk_content)
    
    # 合并
    merged_text = newline.join(merged_chunks)
    
    # 写入修正后文件
    output_path = generate_output_path(args.input, "_fixed")
    with open(output_path, 'w', encoding=args.encoding, newline='') as f:
        f.write(merged_text)
    print(f"修正后文件已保存: {output_path}")
    
    # 处理修改清单
    if args.changes and os.path.exists(args.changes):
        with open(args.changes, 'r', encoding='utf-8') as f:
            changes_data = json.load(f)
        
        changes_text = format_changes_list(changes_data, args.input, total_chars)
        changes_path = generate_output_path(args.input, "_changes")
        with open(changes_path, 'w', encoding='utf-8') as f:
            f.write(changes_text)
        print(f"修改清单已保存: {changes_path}")
    
    # 验证字数
    merged_chars = len(merged_text)
    print(f"\n字数对比: 原文 {total_chars} 字 → 修正后 {merged_chars} 字")
    diff = abs(merged_chars - total_chars)
    if diff > 50:
        print(f"⚠️ 警告: 字数差异较大（{diff}字），请检查是否有内容丢失！")
    else:
        print("✓ 字数差异在正常范围内")


if __name__ == '__main__':
    main()
