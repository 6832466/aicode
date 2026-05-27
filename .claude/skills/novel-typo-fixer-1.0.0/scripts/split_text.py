#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小说推文错别字修正 - 分段预处理脚本
将长文本按自然段落拆分为2000-3000字的块，输出分段信息供AI逐段处理
"""

import sys
import os
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


def split_into_chunks(text, chunk_size=2500):
    """
    按自然段落分割文本为多个块
    - 在换行符处断开，不切断句子
    - 每块约chunk_size字
    """
    # 按换行符拆分为自然段
    paragraphs = text.split('\n')
    
    chunks = []
    current_chunk = []
    current_length = 0
    
    for para in paragraphs:
        para_len = len(para) + 1  # +1 for the newline
        
        # 如果当前块加上这段会超限，且当前块非空，则封块
        if current_length + para_len > chunk_size and current_length > 0:
            chunks.append('\n'.join(current_chunk))
            current_chunk = []
            current_length = 0
        
        current_chunk.append(para)
        current_length += para_len
    
    # 最后一块
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
    
    return chunks


def main():
    parser = argparse.ArgumentParser(description='小说推文错别字修正 - 分段预处理')
    parser.add_argument('input', help='输入文件路径')
    parser.add_argument('-s', '--chunk-size', type=int, default=2500, help='每块字数上限（默认2500）')
    parser.add_argument('-o', '--output', help='输出JSON信息文件路径（可选，默认输出到控制台）')
    args = parser.parse_args()
    
    # 读取文件
    content, encoding = read_file(args.input)
    total_chars = len(content)
    
    # 分段
    chunks = split_into_chunks(content, args.chunk_size)
    
    # 构建分段信息
    result = {
        "source_file": os.path.abspath(args.input),
        "encoding": encoding,
        "total_chars": total_chars,
        "total_chunks": len(chunks),
        "chunk_size_target": args.chunk_size,
        "chunks": []
    }
    
    start_offset = 0
    for i, chunk in enumerate(chunks):
        chunk_info = {
            "index": i + 1,
            "start_offset": start_offset,
            "char_count": len(chunk),
            "preview": chunk[:100] + "..." if len(chunk) > 100 else chunk
        }
        result["chunks"].append(chunk_info)
        start_offset += len(chunk)
    
    # 输出
    output_json = json.dumps(result, ensure_ascii=False, indent=2)
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output_json)
        print(f"分段信息已保存到: {args.output}")
    else:
        print(output_json)
    
    print(f"\n总结: 共 {total_chars} 字, 分为 {len(chunks)} 段, 编码: {encoding}")


if __name__ == '__main__':
    main()
