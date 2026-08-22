"""
通过 REST API / Huntly 批量添加高质量精选量化与财经 RSS 订阅源
"""
import asyncio
from backend.services.api.routers.news import _huntly_request, _unwrap

async def add_feeds():
    print("=== 开始批量添加精选 RSS 订阅源 ===")
    
    # 1. 确保分类文件夹存在
    folders = [
        {'name': 'A股快讯'},
        {'name': '宏观政策'},
        {'name': '量化研究'},
        {'name': '全球市场'}
    ]
    folder_map = {}
    for f in folders:
        try:
            r = await _huntly_request('POST', '/api/setting/folder/save', json={'name': f['name']})
            data = _unwrap(r.json())
            if data and 'id' in data:
                folder_map[f['name']] = data['id']
                print(f"创建分类: {f['name']} (ID: {data['id']})")
        except Exception as e:
            pass

    # 查出现有所有分类
    try:
        r = await _huntly_request('GET', '/api/setting/folder/all')
        for f in (_unwrap(r.json()) or []):
            if f.get('name') and f.get('id'):
                folder_map[f['name']] = f['id']
    except Exception as e:
        print(f"获取分类列表失败: {e}")

    print(f"分类映射表: {folder_map}")

    # 2. 精选高质量财经与量化 RSS 源
    feeds = [
        {'name': '财联社 7x24快讯', 'url': 'https://feedx.net/rss/cls.xml', 'folder': 'A股快讯'},
        {'name': '华尔街见闻 实时快讯', 'url': 'https://feedx.net/rss/wallstreetcn.xml', 'folder': 'A股快讯'},
        {'name': '第一财经 每日精选', 'url': 'https://feedx.net/rss/yicai.xml', 'folder': 'A股快讯'},
        {'name': '东方财富 财经要闻', 'url': 'https://www.eastmoney.com/rss/news.xml', 'folder': 'A股快讯'},
        {'name': '中国人民银行 政策发布', 'url': 'https://rsshub.app/pbc/goutongjiaoliu', 'folder': '宏观政策'},
        {'name': 'arXiv 计算机金融预印本', 'url': 'http://export.arxiv.org/rss/q-fin', 'folder': '量化研究'},
        {'name': 'Microsoft Qlib 更新', 'url': 'https://github.com/microsoft/qlib/releases.atom', 'folder': '量化研究'},
        {'name': '彭博市场动态 (Bloomberg)', 'url': 'https://feeds.bloomberg.com/markets/news.rss', 'folder': '全球市场'}
    ]

    for feed in feeds:
        try:
            print(f"正在订阅: {feed['name']} ({feed['url']}) ...")
            r = await _huntly_request('POST', '/api/setting/feeds/follow', params={'subscribeUrl': feed['url']})
            follow_data = _unwrap(r.json()) or {}
            conn_id = follow_data.get('id') or follow_data.get('connectorId')
            if conn_id:
                folder_id = folder_map.get(feed['folder'])
                await _huntly_request('POST', '/api/setting/feeds/updateSetting', json={
                    'connectorId': conn_id,
                    'name': feed['name'],
                    'folderId': folder_id
                })
                print(f"  ✓ 成功添加: {feed['name']} (ID: {conn_id}, 分类: {feed['folder']})")
            else:
                print(f"  - 已存在或已订阅: {feed['name']}")
        except Exception as e:
            print(f"  ✗ 添加失败 {feed['name']}: {e}")

    print("=== RSS 源批量添加完成 ===")

if __name__ == '__main__':
    asyncio.run(add_feeds())
