"""链接识别与校验工具"""
import re
import hashlib

# 已知平台 URL 模式（快速预检测用，实际解析由 videodl 内部 belongto() 完成）
PLATFORM_PATTERNS = {
    'douyin': [
        r'v\.douyin\.com/[A-Za-z0-9]+/?',
        r'(?:www\.)?douyin\.com/video/\d+',
        r'douyin\.com/user/[A-Za-z0-9_-]+',
        r'www\.iesdouyin\.com/share/video/\d+',
    ],
    'kuaishou': [
        r'v\.kuaishou\.com/[A-Za-z0-9]+/?',
        r'(?:www\.)?kuaishou\.com/short-video/[A-Za-z0-9]+',
        r'(?:www\.)?kuaishou\.com/f/[A-Za-z0-9]+',
    ],
    'bilibili': [
        r'(?:www\.)?bilibili\.com/video/BV[A-Za-z0-9]+',
        r'b23\.tv/[A-Za-z0-9]+',
        r'(?:www\.)?bilibili\.com/bangumi/play/ep\d+',
    ],
    'acfun': [
        r'(?:www\.)?acfun\.cn/v/ac\d+',
        r'(?:www\.)?acfun\.cn/bangumi/aa\d+',
    ],
    'iqiyi': [
        r'(?:www\.)?iqiyi\.com/v_[a-z0-9]+\.html',
    ],
    'youku': [
        r'(?:www\.)?v\.youku\.com/v_show/id_[A-Za-z0-9=]+\.html',
    ],
    'youtube': [
        r'(?:www\.)?youtube\.com/watch\?v=[A-Za-z0-9_-]+',
        r'youtu\.be/[A-Za-z0-9_-]+',
        r'(?:www\.)?youtube\.com/shorts/[A-Za-z0-9_-]+',
    ],
    'mgtv': [
        r'(?:www\.)?mgtv\.com/b/\d+/\d+\.html',
    ],
    'tencent': [
        r'(?:www\.)?v\.qq\.com/x/cover/[a-z0-9]+\.html',
        r'(?:www\.)?v\.qq\.com/x/page/[a-z0-9]+\.html',
    ],
    'sohu': [
        r'(?:www\.)?tv\.sohu\.com/v/\w+\.shtml',
        r'(?:www\.)?my\.tv\.sohu\.com/\w+/\d+\.shtml',
    ],
    'huya': [
        r'(?:www\.)?huya\.com/\d+',
    ],
    'weibo': [
        r'(?:www\.)?weibo\.com/tv/show/\d+:\d+',
        r'(?:www\.)?video\.weibo\.com/show\?fid=\d+:\d+',
    ],
    'zhihu': [
        r'(?:www\.)?zhihu\.com/zvideo/\d+',
        r'(?:www\.)?zhihu\.com/question/\d+/answer/\d+',
    ],
    'rednote': [
        r'(?:www\.)?xiaohongshu\.com/explore/[A-Za-z0-9]+',
        r'(?:www\.)?xhslink\.com/[A-Za-z0-9]+',
    ],
    'xigua': [
        r'(?:www\.)?ixigua\.com/\d+',
        r'(?:www\.)?xigua\.com/\d+',
    ],
    'haokan': [
        r'(?:www\.)?haokan\.baidu\.com/v\?vid=\d+',
    ],
    'pipix': [
        r'(?:www\.)?pipix\.com/item/\d+',
    ],
    'weishi': [
        r'(?:www\.)?weishi\.qq\.com/\w+',
    ],
    'meipai': [
        r'(?:www\.)?meipai\.com/media/\d+',
    ],
    'cctv': [
        r'(?:www\.)?tv\.cctv\.com/\d+/\d+/\d+/\w+\.shtml',
        r'(?:www\.)?cctv\.com/\d+/\d+/\d+/\w+\.shtml',
    ],
    'ted': [
        r'(?:www\.)?ted\.com/talks/[\w-]+',
    ],
    'dailymotion': [
        r'(?:www\.)?dailymotion\.com/video/[a-z0-9]+',
    ],
    'reddit': [
        r'(?:www\.)?reddit\.com/r/\w+/comments/[a-z0-9]+/[\w-]+',
        r'v\.redd\.it/[a-z0-9]+',
    ],
}

# videodl source → (platform_key, display_name, color, folder_name)
SOURCE_MAP = {
    'DouyinVideoClient':          ('douyin',      '抖音',     '#FF0040', '抖音视频'),
    'KuaishouVideoClient':        ('kuaishou',    '快手',     '#FF6600', '快手视频'),
    'BilibiliVideoClient':        ('bilibili',    'B站',      '#FB7299', 'B站视频'),
    'AcFunVideoClient':            ('acfun',       'AcFun',    '#FD4C5D', 'AcFun视频'),
    'IQiyiVideoClient':            ('iqiyi',       '爱奇艺',   '#00BE08', '爱奇艺视频'),
    'YoukuVideoClient':            ('youku',       '优酷',     '#00A7E1', '优酷视频'),
    'TencentVideoClient':          ('tencent',     '腾讯视频', '#0066CC', '腾讯视频'),
    'MGTVVideoClient':             ('mgtv',        '芒果TV',   '#FF6600', '芒果TV视频'),
    'SohuVideoClient':             ('sohu',        '搜狐视频', '#FFD100', '搜狐视频'),
    'YouTubeVideoClient':          ('youtube',     'YouTube',  '#FF0000', 'YouTube视频'),
    'HuyaVideoClient':             ('huya',        '虎牙',     '#FFBB00', '虎牙视频'),
    'WeiboVideoClient':            ('weibo',       '微博',     '#E6162D', '微博视频'),
    'ZhihuVideoClient':            ('zhihu',       '知乎',     '#0066FF', '知乎视频'),
    'RednoteVideoClient':          ('rednote',     '小红书',   '#FE2C55', '小红书视频'),
    'XiguaVideoClient':            ('xigua',       '西瓜视频', '#F94200', '西瓜视频'),
    'HaokanVideoClient':           ('haokan',      '好看视频', '#4A90D9', '好看视频'),
    'PipixVideoClient':            ('pipix',       '皮皮虾',   '#FFC60A', '皮皮虾视频'),
    'PipigaoxiaoVideoClient':      ('pipigaoxiao', '皮皮搞笑', '#FF7A00', '皮皮搞笑视频'),
    'WeishiVideoClient':           ('weishi',      '微视',     '#00C7E3', '微视视频'),
    'MeipaiVideoClient':           ('meipai',      '美拍',     '#E6005C', '美拍视频'),
    'CCTVVideoClient':             ('cctv',        '央视',     '#C41230', '央视视频'),
    'CCTVNewsVideoClient':         ('cctvnews',    '央视新闻', '#C41230', '央视新闻视频'),
    'Ku6VideoClient':              ('ku6',         '酷6',      '#F90',    '酷6视频'),
    'LeshiVideoClient':            ('leshi',       '乐视',     '#E60012', '乐视视频'),
    'PearVideoClient':             ('pear',        '梨视频',   '#A0C75A', '梨视频'),
    'SinaVideoClient':             ('sina',        '新浪视频', '#FF6600', '新浪视频'),
    'M1905VideoClient':            ('m1905',       '1905电影', '#005BAC', '1905电影网视频'),
    'XinpianchangVideoClient':     ('xinpianchang','新片场',   '#00C853', '新片场视频'),
    'XuexiCNVideoClient':          ('xuexicn',     '学习强国', '#C41230', '学习强国视频'),
    'YinyuetaiVideoClient':        ('yinyuetai',   '音悦台',   '#00AAEE', '音悦台视频'),
    'KugouMVVideoClient':          ('kugoumv',     '酷狗MV',   '#00BFFF', '酷狗MV视频'),
    'DongchediVideoClient':        ('dongchedi',   '懂车帝',   '#FFD400', '懂车帝视频'),
    'DuxiaoshiVideoClient':        ('duxiaoshi',   '读小视',   '#FF4757', '读小视视频'),
    'OasisVideoClient':            ('oasis',       '绿洲',     '#00C853', '绿洲视频'),
    'ZuiyouVideoClient':           ('zuiyou',      '最右',     '#FFBA00', '最右视频'),
    'BaiduTiebaVideoClient':       ('baidutieba',  '百度贴吧', '#3385FF', '百度贴吧视频'),
    'DailyMotionVideoClient':      ('dailymotion', 'Dailymotion', '#00D0D0', 'Dailymotion视频'),
    'RedditVideoClient':           ('reddit',      'Reddit',   '#FF4500', 'Reddit视频'),
    'TedVideoClient':              ('ted',         'TED',      '#E62B1E', 'TED视频'),
    'RutubeVideoClient':           ('rutube',      'Rutube',   '#00BFFF', 'Rutube视频'),
    'FoxNewsVideoClient':          ('foxnews',     'Fox News', '#003366', 'FoxNews视频'),
    'WWEVideoClient':              ('wwe',         'WWE',      '#D71618', 'WWE视频'),
    'GeniusVideoClient':           ('genius',      'Genius',   '#FFFF64', 'Genius视频'),
    'KakaoVideoClient':            ('kakao',       'Kakao',    '#FFE812', 'Kakao视频'),
    'PlayerPLVideoClient':         ('playerpl',    'PlayerPL', '#00A6E6', 'PlayerPL视频'),
    'ArteTVVideoClient':           ('artetv',      'ArteTV',   '#FD4D1C', 'ArteTV视频'),
    'TBNUKVideoClient':            ('tbnuk',       'TBNUK',    '#003399', 'TBNUK视频'),
    'ChinaDailyVideoClient':       ('chinadaily',  'ChinaDaily', '#036CB0', 'ChinaDaily视频'),
    'EastDayVideoClient':          ('eastday',     '东方网',   '#C41230', '东方网视频'),
    'PeopleVideoClient':           ('people',      '人民网',   '#C41230', '人民网视频'),
    'XinhuaNetVideoClient':        ('xinhuanet',   '新华网',   '#C41230', '新华网视频'),
    'HuanQiuVideoClient':          ('huanqiu',     '环球网',   '#0066CC', '环球网视频'),
    'MingpaoVideoClient':          ('mingpao',     '明报',     '#003399', '明报视频'),
    'KanKanNewsVideoClient':       ('kankannews',  '看看新闻', '#C41230', '看看新闻视频'),
    'WWW163VideoClient':           ('www163',      '网易视频', '#C41230', '网易视频'),
    'Open163VideoClient':          ('open163',     '网易公开课','#339933', '网易公开课视频'),
    'C56VideoClient':              ('c56',         '56视频',   '#FF6600', '56视频'),
    'CCCVideoClient':              ('ccc',         'CCC',      '#666666', 'CCC视频'),
    'CCtalkVideoClient':           ('cctalk',      'CCtalk',   '#FF7E00', 'CCtalk视频'),
    'BeaconVideoClient':           ('beacon',      'Beacon',   '#336699', 'Beacon视频'),
    'ABCVideoClient':              ('abc',         'ABC',      '#0066CC', 'ABC视频'),
    'WittyTVVideoClient':          ('wittytv',     'WittyTV',  '#FF6600', 'WittyTV视频'),
    'NuVidVideoClient':            ('nuvid',       'NuVid',    '#FF0000', 'NuVid视频'),
    'PlusFIFAVideoClient':         ('plusfifa',    'PlusFIFA', '#00A650', 'PlusFIFA视频'),
    'UnityVideoClient':            ('unity',       'Unity',    '#222C37', 'Unity视频'),
    'WeSingVideoClient':           ('wesing',      'WeSing',   '#FFA500', 'WeSing视频'),
    'SixRoomVideoClient':          ('sixroom',     '六间房',   '#FF6600', '六间房视频'),
    'EyepetizerVideoClient':       ('eyepetizer',  '开眼',     '#000000', '开眼视频'),
}

# 未知平台颜色轮转
_FALLBACK_COLORS = [
    '#0078D4', '#E6162D', '#FF6600', '#FB7299', '#00A870',
    '#8B5CF6', '#F59E0B', '#EC4899', '#06B6D4', '#84CC16',
    '#6366F1', '#14B8A6', '#F43F5E', '#A855F7', '#0EA5E9',
]


def _source_info(source: str) -> tuple:
    """返回 (platform_key, display_name, color, folder_name)"""
    if source in SOURCE_MAP:
        return SOURCE_MAP[source]
    # 尝试通过 platform key 反查
    for s, (key, d, c, f) in SOURCE_MAP.items():
        if key == source:
            return (key, d, c, f)
    # 自动推导
    if source.endswith('VideoClient'):
        name = source[:-12]
    else:
        name = source
    key = name.lower()
    idx = int(hashlib.md5(source.encode()).hexdigest()[:8], 16) % len(_FALLBACK_COLORS)
    return (key, name, _FALLBACK_COLORS[idx], f'{name}视频')


def source_to_platform(source: str) -> str:
    """videodl source 名 → 平台 key"""
    return _source_info(source)[0]


def source_to_display(source_or_key: str) -> str:
    """videodl source 名或平台 key → 中文显示名"""
    return _source_info(source_or_key)[1]


def source_to_color(source_or_key: str) -> str:
    """videodl source 名或平台 key → 主题色"""
    return _source_info(source_or_key)[2]


def source_to_folder(source_or_key: str) -> str:
    """videodl source 名或平台 key → 子文件夹名"""
    return _source_info(source_or_key)[3]


def detect_platform(url: str) -> str | None:
    """快速检测链接所属平台（预填值，解析后会被 videodl source 覆盖）"""
    url = url.strip()
    for platform, patterns in PLATFORM_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return platform
    return None


def extract_video_id(url: str) -> str:
    """从链接中提取视频ID（预填值，解析后会被 videodl 的真实 identifier 覆盖）"""
    # B站: /video/BVxxx 或 bangumi/play/ep123
    m = re.search(r'/video/(BV[A-Za-z0-9]+)', url)
    if m:
        return m.group(1)
    m = re.search(r'/bangumi/play/(ep\d+)', url)
    if m:
        return m.group(1)
    # 抖音/通用: /video/123456789
    m = re.search(r'/video/(\d+)', url)
    if m:
        return m.group(1)
    # 快手: /short-video/xxx 或 /f/xxx
    m = re.search(r'/(?:short-video|f)/([A-Za-z0-9]+)', url)
    if m:
        return m.group(1)
    # 短链接
    m = re.search(r'(?:v\.(?:douyin|kuaishou)|b23\.tv)\.com/([A-Za-z0-9]+)', url)
    if m:
        return m.group(1)
    # AcFun: /v/ac123456
    m = re.search(r'/v/(ac\d+)', url)
    if m:
        return m.group(1)
    # 优酷: id_xxx
    m = re.search(r'id_([A-Za-z0-9=]+)', url)
    if m:
        return m.group(1)
    # YouTube
    m = re.search(r'[?&]v=([A-Za-z0-9_-]+)', url)
    if m:
        return m.group(1)
    return ''


def extract_links(text: str) -> list[str]:
    """从多行文本中提取所有 HTTP 链接，交给 videodl 做平台匹配"""
    lines = text.strip().split('\n')
    links = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        found = re.findall(r'https?://[^\s]+', line)
        for url in found:
            url = url.rstrip('.,;:!?）)')
            links.append(url)
        if not found and line.startswith('http'):
            links.append(line)
    seen = set()
    unique = []
    for link in links:
        if link not in seen:
            seen.add(link)
            unique.append(link)
    return unique[:50]
