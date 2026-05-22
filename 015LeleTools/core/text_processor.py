"""
改文引擎 — AI文本处理核心
"""

import difflib
import re
import logging
from typing import Optional

from app.constants import (
    INSTRUCTION_FIX_TYPOS,
    INSTRUCTION_EXTRACT_NAMES,
    INSTRUCTION_SPLIT_SCENES,
    INSTRUCTION_LONG_SIMPLIFY,
    INSTRUCTION_SCENE_REWRITE,
    INSTRUCTION_CHANGE_PERSON,
    INSTRUCTION_GENDER_SWAP,
)

logger = logging.getLogger(__name__)

# ── 各指令的系统提示词 ──

PROMPT_FIX_TYPOS = """# 小说推文错别字修改与数字转汉字提示词（无标点、分行格式专用）

## 角色
你是一位严谨的小说校对编辑，专门处理**无标点符号、以换行分隔句子**的推文文本。你需要在修正错别字的同时，将除年月日以外的数字转换为汉字。

## 输入格式说明
用户提供的文本具有以下特点：
- **没有标点符号**（句号、逗号、问号、感叹号等均不出现）
- **每行是一个独立的句子或短语**，换行符代替了标点符号的断句功能

## 核心任务
1. **修改错别字**（规则见下文）
2. **数字转汉字**：将除了"年月日"以外的阿拉伯数字转换为中文汉字。转换后，输出文本必须与输入文本在以下方面**完全一致**：
   - 行数不变
   - 每行的换行位置不变
   - 标点符号（原文无标点则不加）
   - 不添加任何注释或说明文字

## 数字转换规则（重要）
- **保留原样**：表示年、月、日的数字。例如：`2026年5月17日`、`23年`（仅当"年"跟在数字后明确表示年份）、`12月`、`5日`。
- **转换为汉字**：
  - 整数：0→零，1→一，2→二，3→三，4→四，5→五，6→六，7→七，8→八，9→九，10→十，11→十一，12→十二，20→二十，100→一百，102→一百零二，1234→一千二百三十四
  - 多位数字：按数字位值转换，不添加"零"以外的多余汉字。例如：`21`→`二十一`，`305`→`三百零五`，`110`→`一百一十`。
  - 序号：`第1章`→`第一章`，`第3条`→`第三条`，`1个`→`一个`，`2次`→`两次`。
  - 小数和百分数：例如 `3.5`→`三点五`，`80%`→`百分之八十`。
  - 电话号码、身份证号、QQ号等长数字串：**保留原阿拉伯数字**（因为这类数字不是数量词，转换为汉字会不可读）。连续数字超过4位且无明显单位（个、次、章等）的，保留原数字。

**简化版转换规则（实用优先）：**
- 凡是单独出现的数字（后面或前面没有"年""月""日"且不是长串ID），都转汉字。
- "年月日"中的数字不动。
- 犹豫时，优先转汉字。

## 错别字判断标准（适用于无标点环境）
依靠上下文语义判断：
- 同音别字：在/再、的/地/得（若原文"跑的很快"改为"跑得很快"）、做/作、已/以、像/向等
- 形近别字：未/末、人/入、日/曰、刺/剌等
- 拼音输入错误："发生"打成"发身" → 改"发身"为"发生"
- 明显漏字：如"我知你来了" → "我知道你来了"（在"知"后加"道"）
- 明显多字：如"他他走了" → "他走了"（删一个"他"）

## 禁止操作
- 不要添加、删除或修改标点符号（原文没有标点就不加）
- 不要合并行或拆分行
- 不要改变词序或句子顺序
- 不要添加注释、括号、高亮、说明文字
- 不要修改作者特有的方言、口语化表达、故意错字
- 不要改动年月日中的数字

## 输出格式
- 只输出修改后的完整文本
- 不要输出任何解释、统计、提示语、开场白
- 严格保持原样的换行和空格

## 示例
**输入：**
他走在昏暗的街上
心里想
这次一定不能在犯同样的错误
那是他第3次犯错了
风很大
吹的他睁不开眼
他在2026年5月17日那天遇到了123个人

**正确输出：**
他走在昏暗的街上
心里想
这次一定不能再犯同样的错误
那是他第三次犯错了
风很大
吹得他睁不开眼
他在2026年5月17日那天遇到了一百二十三个人

## 开始任务
请严格遵循以上规则，修改下方用户提供的小说推文。直接输出修改后的文本，不要回复任何其他内容。"""

PROMPT_EXTRACT_NAMES = """你是一个文本分析助手。请从以下文本中提取所有人物名称和身份。

规则：
1. 识别文中出现的所有人物名称
2. 如果文中有身份描述，一并提取
3. 只输出人名列表，格式：姓名 - 身份（如有），每行一个
4. 不要输出重复的人名
5. 只输出人名列表，不要添加其他内容

请提取以下文本中的人名："""

PROMPT_SPLIT_SCENES = """你是一个视频分镜脚本编辑。请将以下文案拆分成适合AI生成的短段落。

规则：
1. 每段控制在20字左右，保证5秒视频动图效果最佳
2. 按语义切分，不要切断一句话
3. 每段用换行分隔
4. 保持原文内容不变，只做分段
5. 只输出分段后的文本

请将以下文案分镜："""

PROMPT_LONG_SIMPLIFY = """你是一个专业的小说精简编辑。请对以下长篇小说内容进行精简改写。

规则：
1. 保留核心情节和关键对话
2. 删除冗余的描述和心理活动
3. 保持故事连贯性
4. 输出字数约为输入的70%
5. 保持原文风格和人物性格
6. 只输出精简后的文本

请精简以下内容："""

PROMPT_SCENE_REWRITE = """你是一个创意文案改写专家。请对以下分镜文案进行洗稿改写。

规则：
1. 保持20%-30%的改写率，确保降低同质化
2. 保留原文的核心意思和结构
3. 变换句式、用词，但不改变语义
4. 保持分镜格式不变（每行一个分镜）
5. 只输出改写后的文本

请将以下分镜洗稿："""

PROMPT_CHANGE_PERSON = """你是一个文本人称转换助手。请将以下文本中的人称进行转换。

规则：
1. 将第一人称「我」改成第二人称「你」
2. 同时调整相应的动词和语法以保持通顺
3. 保持原文的故事结构和情节
4. 只输出转换后的文本

请转换以下文本的人称："""

PROMPT_GENDER_SWAP = """你是一个创意写作助手。请对以下文本进行性别转换改写。

规则：
1. 将女性化行为改成男性化（如：化妆→刮胡子、穿高跟鞋→穿皮鞋、撒娇→耍酷等）
2. 调整行为、动作、表情更符合目标性别
3. 保持核心情节和故事走向不变
4. 只输出改写后的文本

请对以下文本进行性别转换："""


class TextProcessor:
    """文本处理引擎 — 纯文本操作（不涉及API调用）"""

    @staticmethod
    def format_text(text: str) -> str:
        """格式化文本：去除多余标点（句号、书名号、破折号等），保留冒号、引号、顿号、感叹号"""
        # 去除连续句号
        text = re.sub(r'。{2,}', '', text)
        # 去除行首行尾多余空白
        text = '\n'.join(line.strip() for line in text.splitlines() if line.strip())
        return text

    @staticmethod
    def add_numbers(text: str) -> str:
        """为每行添加序号"""
        lines = text.strip().splitlines()
        return '\n'.join(f"{i+1}. {line}" for i, line in enumerate(lines))

    @staticmethod
    def remove_numbers(text: str) -> str:
        """删除行首序号"""
        return re.sub(r'^\d+[.、．]\s*', '', text, flags=re.MULTILINE)

    @staticmethod
    def batch_replace_names(text: str, name_map: dict) -> str:
        """批量替换人名

        Args:
            text: 原文
            name_map: {原名: 新名}
        """
        result = text
        for old_name, new_name in name_map.items():
            if old_name:
                result = result.replace(old_name, new_name)
        return result

    @staticmethod
    def parse_name_map(text: str) -> dict:
        """解析人名映射文本

        支持格式：
        - 原名1,新名1;原名2,新名2
        - 每行: 原名1,新名1
        """
        name_map = {}
        text = text.strip()
        if not text:
            return name_map

        # 尝试分号分隔
        if ';' in text:
            pairs = text.split(';')
        else:
            pairs = text.splitlines()

        for pair in pairs:
            pair = pair.strip()
            if ',' in pair or '，' in pair:
                parts = re.split(r'[,，]', pair, maxsplit=1)
                if len(parts) == 2:
                    old_name = parts[0].strip()
                    new_name = parts[1].strip()
                    if old_name and new_name:
                        name_map[old_name] = new_name

        return name_map

    @staticmethod
    def split_into_segments(text: str, max_chars: int = 4000) -> list[str]:
        """按行边界将文本切分为不超过 max_chars 字符的段落"""
        lines = text.splitlines()
        segments = []
        buf = []
        buf_len = 0

        for line in lines:
            line_len = len(line) + 1
            if buf and buf_len + line_len > max_chars:
                segments.append('\n'.join(buf))
                buf = []
                buf_len = 0
            buf.append(line)
            buf_len += line_len

        if buf:
            segments.append('\n'.join(buf))

        return segments


def get_instruction_prompt(instruction: str) -> str:
    """获取指令对应的系统提示词"""
    prompts = {
        INSTRUCTION_FIX_TYPOS: PROMPT_FIX_TYPOS,
        INSTRUCTION_EXTRACT_NAMES: PROMPT_EXTRACT_NAMES,
        INSTRUCTION_SPLIT_SCENES: PROMPT_SPLIT_SCENES,
        INSTRUCTION_LONG_SIMPLIFY: PROMPT_LONG_SIMPLIFY,
        INSTRUCTION_SCENE_REWRITE: PROMPT_SCENE_REWRITE,
        INSTRUCTION_CHANGE_PERSON: PROMPT_CHANGE_PERSON,
        INSTRUCTION_GENDER_SWAP: PROMPT_GENDER_SWAP,
    }
    return prompts.get(instruction, "")


def compute_diff(original: str, modified: str) -> str:
    """使用 difflib.SequenceMatcher 生成 HTML diff"""
    matcher = difflib.SequenceMatcher(None, original, modified)
    parts = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            parts.append(f'<span style="color:black;">{_escape_html(original[i1:i2])}</span>')
        elif tag == 'delete':
            parts.append(f'<span style="color:red;text-decoration:line-through;">{_escape_html(original[i1:i2])}</span>')
        elif tag == 'insert':
            parts.append(f'<span style="color:red;font-weight:bold;">{_escape_html(modified[j1:j2])}</span>')
        elif tag == 'replace':
            parts.append(f'<span style="color:red;text-decoration:line-through;">{_escape_html(original[i1:i2])}</span>')
            parts.append(f'<span style="color:red;font-weight:bold;">{_escape_html(modified[j1:j2])}</span>')
    return ''.join(parts)


def _escape_html(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')


def compute_diff_text(original: str, modified: str) -> str:
    """生成纯文本 diff，用 [-删除-] 和 {+新增+} 标记"""
    m, n = len(original), len(modified)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if original[i - 1] == modified[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    i, j = m, n
    ops = []
    while i > 0 or j > 0:
        if i > 0 and j > 0 and original[i - 1] == modified[j - 1]:
            ops.append(('keep', original[i - 1]))
            i -= 1
            j -= 1
        elif j > 0 and (i == 0 or dp[i][j - 1] >= dp[i - 1][j]):
            ops.append(('add', modified[j - 1]))
            j -= 1
        else:
            ops.append(('del', original[i - 1]))
            i -= 1

    parts = []
    i = 0
    while i < len(ops):
        op, ch = ops[i]
        if op == 'keep':
            parts.append(ch)
            i += 1
        elif op == 'del':
            buf_del = []
            while i < len(ops) and ops[i][0] == 'del':
                buf_del.append(ops[i][1])
                i += 1
            parts.append('[-' + ''.join(buf_del) + '-]')
        elif op == 'add':
            buf_add = []
            while i < len(ops) and ops[i][0] == 'add':
                buf_add.append(ops[i][1])
                i += 1
            parts.append('{+' + ''.join(buf_add) + '+}')

    return ''.join(parts)


def count_characters(text: str) -> int:
    """统计字数（中文字符）"""
    count = 0
    for ch in text:
        if '一' <= ch <= '鿿' or '　' <= ch <= '〿' or '＀' <= ch <= '￯':
            count += 1
        elif ch.isdigit():
            count += 1
    return count
