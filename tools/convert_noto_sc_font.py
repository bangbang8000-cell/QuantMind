"""把 NotoSansCJK-*.ttc 的 SC 子字体转成 reportlab 可用的 TrueType 字体。

背景：docker/training/fonts/NotoSansCJK.ttf 是 JP 子集（缺 132 个简体字，
如 户/强/卖/买/产/仓），reportlab 遇到缺字静默回退 CID 字体（HYZhongYuanB5），
PDF 里混字体渲染就乱。NotoSansCJKSC-*.ttf（官方 SC 版）是 CFF/PostScript 轮廓，
reportlab 的 TTFont 不支持。

流程（需 fontTools + ufo2ft + cu2qu + defcon + extractor，容器内已装）：
  1. TTCollection 取 index 2 子字体（Noto Sans CJK SC / SC Bold）
  2. extractUFO → defcon UFO（CFF 轮廓）
  3. ufo2ft.compileTTF(skipFeatureCompilation=True)：CFF→TrueType 二次曲线
     - aalt 特性含脚本语句 feaLib 编译报错，跳过（正文渲染不需要连字特性）
     - post 表 format 2 名字索引超 unsigned short（4.4 万 glyph），删掉重建
  4. 补 post format 3.0 表（reportlab 必须读 post）
  5. 子集化到 GB2312+常用符号（6908 字形，2MB，PDF 嵌入体积可控）

输出（docker/training/fonts/）：
  - NotoSansCJKSC-Regular-ttf.ttf / -Bold-ttf.ttf        全量（19MB，兜底）
  - NotoSansCJKSC-Regular-ttf-subset.ttf / -Bold-...     子集（2MB，md_to_pdf_report 首选）

用法：容器内 python3 tools/convert_noto_sc_font.py
"""

import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

FONT_DIR = Path(__file__).resolve().parents[1] / "docker" / "training" / "fonts"

# GB2312 一级(0xB0A1-0xD7F9) + 二级(0xD8A1-0xF7FE) + 常用符号 + ASCII
def _gb2312_charset() -> str:
    chars = set()
    for hi in list(range(0xB0, 0xD8)) + list(range(0xD8, 0xF8)):
        for lo in range(0xA1, 0xFF):
            if hi == 0xD7 and lo > 0xF9:
                continue
            if hi == 0xF7 and lo > 0xFE:
                continue
            try:
                chars.add(bytes([hi, lo]).decode("gb2312"))
            except UnicodeDecodeError:
                pass
    extra = (
        "＋－×÷＝≈±％‰°℃　、。《》（）【】「」『』—…·“”‘’"
        "：；？！，．／｜＆％①②③④⑤⑥⑦⑧⑨⑩"
        + "".join(chr(c) for c in range(0x20, 0x7F))
    )
    chars.update(extra)
    return "".join(sorted(chars))


def convert_one(ttc_path: Path, out_ttf: Path) -> None:
    from fontTools.ttLib import TTCollection, TTFont, newTable
    from extractor import extractUFO
    from ufo2ft import compileTTF
    from defcon import Font

    coll = TTCollection(str(ttc_path))
    src = coll.fonts[2]  # index 2 = Noto Sans CJK SC
    print(f"提取 SC 子字体: {src['name'].getDebugName(4)}")
    tmp_otf = Path("/tmp") / (ttc_path.stem + ".otf")
    src.save(str(tmp_otf))

    ufo = Font()
    extractUFO(str(tmp_otf), ufo)
    otf = compileTTF(
        ufo, inplace=False, skipFeatureCompilation=True, removeOverlaps=False
    )
    if "post" in otf:
        del otf["post"]
    post = newTable("post")
    post.formatType = 3.0
    post.italicAngle = 0
    post.underlinePosition = -150
    post.underlineThickness = 50
    post.isFixedPitch = 0
    post.minMemType42 = 0
    post.maxMemType42 = 0
    post.minMemType1 = 0
    post.maxMemType1 = 0
    otf["post"] = post
    otf.save(str(out_ttf))

    check = TTFont(str(out_ttf))
    cmap = check.getBestCmap()
    test = "工业富联股东户数强买卖业绩产仓严（）：，。％×＋－"
    missing = [c for c in test if ord(c) not in cmap]
    print(f"→ {out_ttf.name}: {out_ttf.stat().st_size/1e6:.1f}MB, "
          f"cmap={len(cmap)}, 测试缺字={missing}")


def subset_one(full_ttf: Path, out_ttf: Path) -> None:
    from fontTools import subset
    from fontTools.ttLib import TTFont

    subset.main([
        str(full_ttf), f"--text={_gb2312_charset()}",
        f"--output-file={out_ttf}", "--no-hinting", "--notdef-outline",
    ])
    check = TTFont(str(out_ttf))
    cmap = check.getBestCmap()
    print(f"→ {out_ttf.name}: {out_ttf.stat().st_size/1e6:.1f}MB, cmap={len(cmap)}")


def main() -> None:
    for suffix, ttc_name in (("Regular", "NotoSansCJK-Regular.ttc"), ("Bold", "NotoSansCJK-Bold.ttc")):
        full = FONT_DIR / f"NotoSansCJKSC-{suffix}-ttf.ttf"
        subset_out = FONT_DIR / f"NotoSansCJKSC-{suffix}-ttf-subset.ttf"
        if full.exists():
            print(f"{full.name} 已存在，跳过转换")
        else:
            convert_one(FONT_DIR / ttc_name, full)
        if subset_out.exists():
            print(f"{subset_out.name} 已存在，跳过子集化")
        else:
            subset_one(full, subset_out)


if __name__ == "__main__":
    sys.exit(main())
