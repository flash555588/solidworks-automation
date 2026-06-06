# solidworks-automation — 项目规范

## 坐标系参考

| 平面 | 世界位置 | 法向 | 草图 X | 草图 Y | cut_blind 默认方向 |
|------|----------|------|--------|--------|-------------------|
| Top Plane (上视) | XY, Z=0 | +Z | 世界 X | 世界 Y | **−Z** (向下) |
| Front Plane (前视) | XZ, Y=0 | +Y | 世界 X | 世界 Z | **−Y** (向后) |
| Right Plane (右视) | YZ, X=0 | +X | 世界 Y | 世界 Z | **−X** (向左) |

**X 轴方向的偏移平面（截面放样）必须用 Right Plane，不能用 Front Plane。**

---

## 切割操作规范

### 核心规则：优先用 `cut_midplane`

`cut_blind` 默认方向由平面法向决定，容易切到空空间。  
`cut_midplane(d)` 从草图平面双向对称切割 ±d/2，**始终**能切到草图平面两侧的实体。

```python
# 正确 — 底面口袋（实体在 Top Plane 上方 Z>0）
part.select_plane("Top Plane")
with part.sketch() as sk:
    sk.corner_rectangle(x1, y1, x2, y2)
part.features.cut_midplane(pocket_depth * 2)

# 错误 — 默认向 −Z 切，切到空空间
part.features.cut_blind(pocket_depth)          # WRONG on Top Plane

# 可用但需明确意图
part.features.cut_blind(depth, reverse=True)   # 明确向 +Z 切
```

| 场景 | 推荐方法 |
|------|----------|
| 底面口袋（实体在 +Z） | `cut_midplane(depth * 2)` |
| 贯穿切割 | `cut_midplane(mm(200))` — 超过最大体高即可 |
| 确定方向的单向切 | `cut_blind(depth, reverse=True/False)` 并注释方向 |

---

## 草图轮廓规范

### 核心规则：只用保证闭合的原语

`circle` 和 `corner_rectangle` 自动产生闭合轮廓，无需额外约束。  
手动 `line + arc` 拼接的轮廓端点虽然数值重合，但 SOLIDWORKS 视为独立点，  
`select_closed_contours()` 找不到封闭区域。

```python
# 正确
sk.corner_rectangle(x1, y1, x2, y2)   # 矩形
sk.circle(cx, cy, r)                   # 圆
sk.oblong(cx, cy, length, width)       # 圆角槽（SOLIDWORKS 2007+）

# 错误 — 没有 Coincident 约束就不会被识别为封闭
sk.line(...)
sk.arc(...)                            # WRONG — 需显式 sk.coincident() 连接端点
```

当必须使用 `line + arc` 时，每对相接端点都要调用 `sk.coincident(p1, p2)`。

---

## 放样（Loft）规范

```python
# 1. 创建截面草图，保存特征引用
profiles = []
for x_off, hw, hh, label in SECTIONS:
    part.clear_selection()
    part.select_plane("Right Plane")
    plane = part.features.offset_plane(abs(x_off), flip=(x_off < 0))
    plane.Name = f"Plane {label}"
    part.clear_selection()
    part.select_object(plane)
    with part.sketch() as sk:
        sk.ellipse(0, hh, hw, hh, 0, 2 * hh)   # 底对齐椭圆
    profiles.append(part.rename_last_feature(f"Profile {label}"))

# 2. 选择所有截面（mark=1），再调用 loft_boss
part.clear_selection()
part.select_object(profiles[0], mark=1)
for p in profiles[1:]:
    part.select_object(p, append=True, mark=1)
part.features.loft_boss(closed=False, keep_tangency=False)
```

---

## 文件编辑规范

`Edit` 工具依赖精确字符串匹配，多次编辑后位置漂移会导致内容错位。

| 场景 | 工具 |
|------|------|
| 修改 1–5 行 | `Edit` |
| 大范围重构、结构混乱、重复代码块 | `Write`（完整重写） |

**每次 `Edit` 后如需继续编辑同一文件，必须先 `Read` 确认当前状态。**

---

## 代码质量规范

- `except` 必须带异常变量并调用 `logger.debug(...)` — 禁止裸 `except: pass`
- `logger.xxx(f"...")` 格式化字符串改用 `%` 参数：`logger.debug("msg %s", val)`
- 每个 `cut_*` / `extrude_*` 调用后立即 `rename_last_feature`
- `feature_errors()` 在 `rebuild()` 后检查，有错误时打印明细

---

## 调试记录

详见 `DEBUG_LOG.md`。  
核心教训（2026-06-05）：

1. `cut_blind` 在 Top Plane 默认向 −Z，实体在 +Z 时必须用 `cut_midplane`
2. `line + arc` 拼接无约束 → `select_closed_contours` 找不到封闭轮廓
3. 放样截面应偏移自 Right Plane（法向 X），不是 Front Plane（法向 Z）
4. 结构混乱时用 `Write` 重写，不要用 `Edit` 打补丁
