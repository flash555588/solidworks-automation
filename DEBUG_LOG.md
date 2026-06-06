# 无线鼠标建模问题日志

## 问题概述
多次尝试用 SOLIDWORKS COM API 创建流线型无线鼠标模型，反复遇到 `cut` 操作失败和文件损坏问题。

---

## 迭代记录

### 第 1 次 – 电池盖凹槽 cut_blind 失败
**代码位置**: `examples/model_wireless_mouse.py` 初始版本
**错误**:
```
solidworks_com.errors.SolidWorksError: Failed to create blind cut
```
**根因**:
- 在 `Top Plane`（Z=0，底面）上画矩形后调用 `cut_blind(COVER_DEPTH)`
- Loft 生成的实体位于 Z>0 区域（底部在 Z=0，顶部在 Z=72）
- `cut_blind` 默认从草图平面向 **-Z 方向**（向下）切割
- 切割方向上没有实体，切到了空的空间
**修复方向**: 改用 `cut_midplane` 或 `reverse=True` 向上切

---

### 第 2 次 – 电池仓 cut_blind 失败（添加 select_closed_contours 后）
**代码位置**: 第 1 次修复后的版本
**错误**:
```
solidworks_com.errors.SolidWorksError: Failed to create blind cut
```
**根因**:
- 虽然添加了 `sk.select_closed_contours()` 显式选择轮廓
- 但 `cut_blind` 从 `Top Plane`（底面）默认向下切（-Z）
- 实体在 +Z 方向，切割方向仍然对着空空间
**修复方向**: 使用 `cut_midplane(depth*2)` 让切割双向对称，确保总有一侧进入实体

---

### 第 3 次 – 接收器槽 cut_midplane 失败
**代码位置**: 第 2 次修复后的版本
**错误**:
```
solidworks_com.errors.SolidWorksError: Failed to create mid-plane cut
```
**根因**:
- 在 `Right Plane`（XZ 平面，法向 Y）上画矩形
- `Right Plane` 草图坐标系：X=世界 X，Y=世界 Z
- 代码按 `corner_rectangle(RECEIVER_X - hl, -hw, RECEIVER_X + hl, hw)` 绘制
- 但 `cut_midplane(MOUSE_WIDTH)` 沿 Y 轴切割，草图在 Y=0 平面
- 矩形轮廓与切割方向平行，没有形成有效的贯穿切割
**修复方向**: 将接收器槽改到 `Top Plane`（XY 平面）上绘制，用 `cut_midplane` 沿 Z 轴切

---

### 第 4 次 – 脚本成功运行（简化版）
**结果**: `Saved: outputox_mouse.SLDPRT`
**问题**: 模型是一个长方体加几个矩形切割，**外形完全不像鼠标**
- 用户反馈："这个模型根本不是鼠标，请认真设计一下"

---

### 第 5 次 – 多截面 Loft 方案 + 长圆形电池仓失败
**代码位置**: 多截面放样版本
**错误**:
```
solidworks_com.errors.SolidWorksError: No closed sketch contours found
```
**根因**:
- 电池仓尝试用 **2 条 line + 2 个 arc** 拼接成长圆形槽
- `sk.line(...)` + `sk.arc(...)` 创建的线段和圆弧端点理论上重合
- 但 SOLIDWORKS 没有自动识别为封闭轮廓（缺少几何约束）
- `select_closed_contours()` 找不到任何封闭区域
**深层原因**:
- `CreateArc` 和 `CreateLine` 是独立的几何实体
- 端点坐标虽然数值相等，但 SOLIDWORKS 内部可能视为独立点
- 需要显式添加 `Coincident` 约束才能确保轮廓闭合
- 但代码中没有调用约束添加
**修复方向**: 改用简单可靠的 `corner_rectangle`（矩形）代替复杂的长圆形拼接

---

### 第 6 次 – 文件被 edit 工具严重破坏
**代码位置**: `examples/model_wireless_mouse.py`
**现象**:
- 使用 `edit` 工具替换代码段时，由于行号偏移，替换了错误的位置
- 导致 Loft 主体代码被电池仓代码覆盖，后续代码重复出现
- 文件中出现大量重复和断裂的代码块
**根因**:
- `edit` 工具依赖精确的行号，多次编辑后行号偏移
- 没有每次编辑后重新 `read` 文件确认状态
- 编辑范围过大（一次性替换多行），导致错误扩散
**修复方向**: 使用 `write` 工具完整重写文件，而非增量编辑

---

## 核心问题分类

| 类别 | 具体问题 | 影响 |
|------|----------|------|
| **切割方向** | `cut_blind` 默认方向与实体位置不匹配 | cut 操作反复失败 |
| **轮廓闭合** | arc+line 拼接的轮廓缺少几何约束 | `select_closed_contours` 找不到封闭区域 |
| **坐标系混淆** | `Right Plane` vs `Top Plane` 的草图坐标轴对应关系不清 | 接收器槽位置错误 |
| **工具误用** | `edit` 工具行号漂移导致文件损坏 | 代码结构完全混乱 |
| **外形设计** | 纯方块+切割无法实现流线型人体工学外形 | 用户不满意 |

---

## 关键 API 行为（已验证）

1. **`cut_blind(depth)`**: 从草图平面向 **默认方向** 单向切割。在 `Top Plane` 上默认向 **-Z**（向下）。如果实体在 +Z，需用 `reverse=True` 或改用 `cut_midplane`。

2. **`cut_midplane(depth)`**: 从草图平面向 **两侧对称** 切割，总深度 = `depth`。在 `Top Plane` 上切 `[-depth/2, +depth/2]`。适合确保切割能进入实体。

3. **`select_closed_contours()`**: 要求草图中的几何实体 **已闭合** 且 **有明确约束**。简单的 `circle` 和 `corner_rectangle` 自动闭合；手动的 `line`+`arc` 拼接需要显式约束才能被识别。

4. **草图坐标系**:
   - `Top Plane`: 草图 X=世界 X，草图 Y=世界 Y
   - `Front Plane`: 草图 X=世界 Y，草图 Y=世界 Z
   - `Right Plane`: 草图 X=世界 X，草图 Y=世界 Z

5. **`offset_plane(distance, flip)`**: `flip=True` 反转偏移方向。`Front Plane` 法向 +X，`flip=True` 朝 -X。

---

## 后续建议

1. **切割操作**: 统一使用 `cut_midplane(depth*2)` 代替 `cut_blind`，避免方向问题
2. **轮廓绘制**: 只用 `circle` 和 `corner_rectangle`，避免手动 line+arc 拼接
3. **文件编辑**: 代码结构混乱时直接用 `write` 重写，不用 `edit` 修修补补
4. **外形设计**: 若需真正流线型，考虑：
   - 安装 `build123d` 用 Python 生成 STEP 再导入 SOLIDWORKS
   - 或使用 SOLIDWORKS 的 `spline` + `loft` 创建更精确的有机形状
5. **验证流程**: 每次修改后先语法检查 (`py -m py_compile`)，再运行

---

*日志生成时间: 2026-06-05*
*涉及文件: `examples/model_wireless_mouse.py`, `solidworks_com/features.py`, `solidworks_com/sketch.py`*
*参考示例: `examples/test_contour_selection.py`, `examples/test_loft_smoke.py`, `examples/model_bracket.py`*
