import asyncio
from backend.services.api.routers.news import _huntly_request, _unwrap

async def organize():
    print("=== 整理 Huntly 分类与订阅源 ===")
    r = await _huntly_request("GET", "/api/connector/folder-connectors")
    body = _unwrap(r.json()) or {}
    ffc = body.get("folderFeedConnectors") or []
    
    # 查找分类 ID
    folder_map = {}
    for f in ffc:
        if f.get("name") and f.get("id"):
            folder_map[f["name"]] = f["id"]
            
    print(f"现有分类: {folder_map}")
    
    # 遍历未分组 connector
    for f in ffc:
        if f.get("id") is None:
            for item in f.get("connectorItems") or []:
                cid = item.get("id")
                name = item.get("name") or ""
                target_folder_name = "A股快讯"
                if "qlib" in name.lower() or "arxiv" in name.lower():
                    target_folder_name = "量化研究"
                elif "监管" in name or "政策" in name:
                    target_folder_name = "宏观与监管"
                
                target_fid = folder_map.get(target_folder_name)
                if target_fid and cid:
                    print(f"移动源「{name}」(ID: {cid}) 到分类「{target_folder_name}」(ID: {target_fid}) ...")
                    await _huntly_request("POST", "/api/setting/feeds/updateSetting", json={
                        "connectorId": cid,
                        "folderId": target_fid
                    })
    print("=== 整理完成 ===")

if __name__ == '__main__':
    asyncio.run(organize())
