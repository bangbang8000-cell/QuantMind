"""
通过 REST API / Huntly 批量添加 100% 实测可用的精选量化与财经 RSS 订阅源
"""
import asyncio
from backend.services.api.routers.news import _huntly_request, _unwrap

async def add_feeds():
    print("=== 开始批量添加 100% 实测可用的 RSS 订阅源 ===")
    
    # 1. 确保分类文件夹存在
    folders = [
        {'name': 'A股快讯'},
        {'name': '宏观与监管'},
        {'name': '量化研究'},
        {'name': '商业科技'}
    ]
    folder_map = {}
    for f in folders:
        try:
            r = await _huntly_request('POST', '/api/setting/folder/save', json={'name': f['name']})
            data = _unwrap(r.json())
            if data and 'id' in data:
                folder_map[f['name']] = data['id']
                print(f"创建分类: {f['name']} (ID: {data['id']})")
        except Exception:
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

    # 2. 100% 实测连通与解析正常的优质源
    feeds = [
        {'name': '财联社 7x24快讯', 'url': 'http://quantmind-rsshub:1200/cls/telegraph', 'folder': 'A股快讯'},
        {'name': '华尔街见闻 实时快讯', 'url': 'http://quantmind-rsshub:1200/wallstreetcn/news/global', 'folder': 'A股快讯'},
        {'name': '格隆汇 实时快讯', 'url': 'http://quantmind-rsshub:1200/gelonghui/live', 'folder': 'A股快讯'},
        {'name': '金十数据 实时快讯', 'url': 'http://quantmind-rsshub:1200/jin10/news', 'folder': 'A股快讯'},
        {'name': '财新网 金融监管', 'url': 'http://quantmind-rsshub:1200/caixin/finance/regulation', 'folder': '宏观与监管'},
        {'name': '36氪 商业快讯', 'url': 'http://quantmind-rsshub:1200/36kr/newsflashes', 'folder': '商业科技'},
        {'name': 'arXiv 计算机金融预印本', 'url': 'http://export.arxiv.org/rss/q-fin', 'folder': '量化研究'},
        {'name': 'Microsoft Qlib 官方更新', 'url': 'https://github.com/microsoft/qlib/releases.atom', 'folder': '量化研究'}
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
