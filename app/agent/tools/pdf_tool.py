"""刀版 PDF 拆面工具。

礼盒的刀版图（拼版图）里，每一个面都是一个带填充色的矩形，折线、裁切线、
尺寸标注都是独立的矢量路径。所以不需要让视觉模型去猜边界 —— 直接从
`get_drawings()` 里把填充矩形捞出来，就是精确到 pt 的面。

流程：找面 -> 按间距聚成盒子（外盒/内盒）-> 用上方标题给盒子命名 ->
按 clip 逐面渲染成 PNG。
"""

import re
from pathlib import Path

import pymupdf
from langchain_core.tools import tool

from app.agent.backend import FILES_DIR, build_backend

PT_PER_CM = 72 / 2.54

# 小于这个边长的填充矩形是色块 / 图标之类的噪点，不是面
MIN_FACE_CM = 1.0
# 面积超过页面这个比例的矩形是背景板，不是面
MAX_FACE_PAGE_RATIO = 0.5
# 两个面的间距小于这个值就算同一个盒子。刀版里同一个盒子的相邻面只隔着
# 一条折线（这份文件里约 6pt），不同盒子之间通常隔着几百 pt
GROUP_GAP_PT = 40
# 判断"这些面是否排成一行/一列"时允许的边缘偏差
ALIGN_TOL_PT = 12
# 认标题时，字号差在这个比例内视为同一级，再按远近取最近的那个
TITLE_SIZE_RATIO = 0.8

DEFAULT_DPI = 200
MAX_DPI = 600


def _resolve_pdf(file_path: str) -> Path:
    """把模型给的路径解析成真实文件。

    模型可能给两种路径：agent 文件系统里的虚拟路径（/xx.pdf，实际在
    FILES_DIR 下），或者用户在对话里贴的宿主机真实路径。两种都试一遍。
    """
    candidates = [Path(file_path).expanduser()]
    if file_path.startswith("/"):
        candidates.append(FILES_DIR / file_path.lstrip("/"))
    else:
        candidates.append(FILES_DIR / file_path)

    for path in candidates:
        if path.is_file():
            return path

    msg = f"找不到文件：{file_path}"
    raise FileNotFoundError(msg)


def _cm(pt: float) -> float:
    return round(pt / PT_PER_CM, 1)


def _collect_faces(page: pymupdf.Page) -> list[pymupdf.Rect]:
    """捞出这一页上所有"面"级别的填充矩形。"""
    min_pt = MIN_FACE_CM * PT_PER_CM
    max_area = page.rect.get_area() * MAX_FACE_PAGE_RATIO

    faces: list[pymupdf.Rect] = []
    for drawing in page.get_drawings():
        # 只描边不填充的是折线 / 标注线，不是面
        if drawing.get("fill") is None:
            continue
        for item in drawing["items"]:
            if item[0] != "re":
                continue
            rect = item[1]
            if rect.width < min_pt or rect.height < min_pt:
                continue
            if rect.get_area() > max_area:
                continue
            faces.append(rect)
    return faces


def _gap(a: pymupdf.Rect, b: pymupdf.Rect) -> float:
    """两个矩形在 x / y 方向上的最大间距，重叠时为 0。"""
    dx = max(0.0, max(a.x0, b.x0) - min(a.x1, b.x1))
    dy = max(0.0, max(a.y0, b.y0) - min(a.y1, b.y1))
    return max(dx, dy)


def _group_faces(faces: list[pymupdf.Rect]) -> list[list[pymupdf.Rect]]:
    """按间距把面聚成一个个盒子（并查集）。"""
    parent = list(range(len(faces)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(faces)):
        for j in range(i + 1, len(faces)):
            if _gap(faces[i], faces[j]) <= GROUP_GAP_PT:
                parent[find(i)] = find(j)

    buckets: dict[int, list[pymupdf.Rect]] = {}
    for idx, rect in enumerate(faces):
        buckets.setdefault(find(idx), []).append(rect)

    groups = list(buckets.values())
    # 左上角在前，保证输出顺序和看图顺序一致
    groups.sort(key=lambda g: (min(r.y0 for r in g), min(r.x0 for r in g)))
    return groups


def _bbox(rects: list[pymupdf.Rect]) -> pymupdf.Rect:
    box = pymupdf.Rect(rects[0])
    for r in rects[1:]:
        box |= r
    return box


def _group_label(page: pymupdf.Page, box: pymupdf.Rect, index: int) -> str:
    """用盒子正上方最近的大字标题给它命名，比如"盖板外侧""内盒"。

    尺寸标注（"27 cm"）字号很小，正文说明（"(包边肤感膜 UV印刷)"）虽然离得
    更近但字号只有标题的一半，所以先按字号挑，再按远近挑。
    """
    candidates: list[tuple[float, float, str]] = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                text = span["text"].strip()
                if not text:
                    continue
                x0, y0, x1, y1 = span["bbox"]
                # 必须在盒子上方，且横向落在盒子的范围内
                if y1 > box.y0:
                    continue
                if not (box.x0 <= (x0 + x1) / 2 <= box.x1):
                    continue
                candidates.append((span["size"], y1, text))

    if not candidates:
        return f"组{index}"

    max_size = max(c[0] for c in candidates)
    titles = [c for c in candidates if c[0] >= max_size * TITLE_SIZE_RATIO]
    # 同一级字号里取最靠近盒子的（y1 最大）
    return max(titles, key=lambda c: c[1])[2]


def _name_faces(rects: list[pymupdf.Rect]) -> list[tuple[str, pymupdf.Rect]]:
    """给盒子里的每个面起名字。

    横排/竖排的展开图（比如盖板外侧的 27+4+27+4+26）按顺序叫 面N，明显窄的
    那几条是折边；十字形展开图（内盒）按相对主面的方位叫 底面 / 上侧墙 …
    """
    same_row = all(
        abs(r.y0 - rects[0].y0) <= ALIGN_TOL_PT and abs(r.y1 - rects[0].y1) <= ALIGN_TOL_PT for r in rects
    )
    same_col = all(
        abs(r.x0 - rects[0].x0) <= ALIGN_TOL_PT and abs(r.x1 - rects[0].x1) <= ALIGN_TOL_PT for r in rects
    )

    if same_row or same_col:
        ordered = sorted(rects, key=lambda r: r.x0 if same_row else r.y0)
        span = max((r.width if same_row else r.height) for r in ordered)
        named: list[tuple[str, pymupdf.Rect]] = []
        face_no = fold_no = 0
        for rect in ordered:
            # 明显比主面窄的是折边（书脊），单独编号
            if (rect.width if same_row else rect.height) < span * 0.35:
                fold_no += 1
                named.append((f"折边{fold_no}", rect))
            else:
                face_no += 1
                named.append((f"面{face_no}", rect))
        return named

    # 十字形：面积最大的是底面，其余按方位命名
    main = max(rects, key=lambda r: r.get_area())
    named = [("底面", main)]
    for rect in sorted((r for r in rects if r is not main), key=lambda r: (r.y0, r.x0)):
        cy, cx = (rect.y0 + rect.y1) / 2, (rect.x0 + rect.x1) / 2
        if cy < main.y0:
            side = "上侧墙"
        elif cy > main.y1:
            side = "下侧墙"
        elif cx < main.x0:
            side = "左侧墙"
        elif cx > main.x1:
            side = "右侧墙"
        else:
            side = "内页"
        named.append((side, rect))
    return named


def _safe(name: str) -> str:
    """清掉文件名里不安全的字符，中文保留。"""
    return re.sub(r"[^\w一-鿿.-]+", "_", name).strip("_") or "face"


def _analyze(pdf_path: Path) -> list[dict]:
    """解析出每一页上的盒子和面，不写文件。"""
    result: list[dict] = []
    with pymupdf.open(pdf_path) as doc:
        for page_no, page in enumerate(doc, 1):
            faces = _collect_faces(page)
            if not faces:
                continue
            for group_no, group in enumerate(_group_faces(faces), 1):
                box = _bbox(group)
                result.append(
                    {
                        "page": page_no,
                        "label": _group_label(page, box, group_no),
                        "faces": [
                            {
                                "name": name,
                                "width_cm": _cm(rect.width),
                                "height_cm": _cm(rect.height),
                                "rect": [round(v, 1) for v in (rect.x0, rect.y0, rect.x1, rect.y1)],
                            }
                            for name, rect in _name_faces(group)
                        ],
                    }
                )
    return result


@tool
def inspect_box_pdf(file_path: str) -> dict:
    """解析礼盒刀版 PDF，列出里面有哪些盒子、每个盒子有哪些面和尺寸。

    只做解析不生成图片，用于在切分前向用户确认结构。

    Args:
        file_path: PDF 路径，可以是 agent 文件系统里的路径，也可以是用户给的本机路径。
    """
    try:
        pdf_path = _resolve_pdf(file_path)
    except FileNotFoundError as e:
        return {"error": str(e)}

    groups = _analyze(pdf_path)
    if not groups:
        return {"error": "没有在这个 PDF 里识别到刀版面（找不到填充矩形）"}

    return {
        "file": pdf_path.name,
        "groups": [
            {
                "page": g["page"],
                "label": g["label"],
                "face_count": len(g["faces"]),
                "faces": [
                    {"name": f["name"], "size_cm": f"{f['width_cm']}x{f['height_cm']}"} for f in g["faces"]
                ],
            }
            for g in groups
        ],
    }


@tool
def split_box_pdf(file_path: str, dpi: int = DEFAULT_DPI, label: str | None = None) -> dict:
    """把礼盒刀版 PDF 按每个面切分成单独的 PNG 图片并保存。

    外盒（盖板）和内盒都会被切开，每个面一张图，尺寸标注线不会混进去。

    Args:
        file_path: PDF 路径，可以是 agent 文件系统里的路径，也可以是用户给的本机路径。
        dpi: 输出分辨率，默认 200，最高 600。印刷用途建议 300。
        label: 只切某一个盒子，传它的名字（比如"内盒"）。不传则全部切。
    """
    try:
        pdf_path = _resolve_pdf(file_path)
    except FileNotFoundError as e:
        return {"error": str(e)}

    dpi = max(72, min(int(dpi), MAX_DPI))
    groups = _analyze(pdf_path)
    if label:
        groups = [g for g in groups if g["label"] == label]
    if not groups:
        return {"error": f"没有可切分的面（label={label!r}）" if label else "没有在这个 PDF 里识别到刀版面"}

    out_dir = f"/pdf_faces/{_safe(pdf_path.stem)}"
    scale = pymupdf.Matrix(dpi / 72, dpi / 72)
    payload: list[tuple[str, bytes]] = []
    meta: list[dict] = []

    with pymupdf.open(pdf_path) as doc:
        for group in groups:
            page = doc[group["page"] - 1]
            for seq, face in enumerate(group["faces"], 1):
                rect = pymupdf.Rect(*face["rect"])
                # alpha=False：面都是实心的，不留透明通道能省不少体积
                pix = page.get_pixmap(matrix=scale, clip=rect, alpha=False)
                size = f"{face['width_cm']}x{face['height_cm']}cm"
                name = _safe(f"{group['label']}_{seq:02d}_{face['name']}_{size}")
                path = f"{out_dir}/{name}.png"
                payload.append((path, pix.tobytes("png")))
                meta.append(
                    {
                        "path": path,
                        "group": group["label"],
                        "face": face["name"],
                        "size_cm": size,
                        "pixels": f"{pix.width}x{pix.height}",
                    }
                )

    failed = [r.path for r in build_backend().upload_files(payload) if r.error]
    if failed:
        return {"error": f"以下文件保存失败：{failed}"}

    return {"dir": out_dir, "count": len(meta), "files": meta}
