# solidworks-com 全面修复计划

## 目标
修复代码审计报告中列出的所有问题（P0/P1/P2）。

## 阶段

### Stage 1 — P0 立即修复（可并行）
1. **app.py** — 添加 `atexit` COM 公寓清理钩子，修复异常路径泄漏
2. **__init__.py** — 延迟导入，消除循环导入风险
3. **model.py** — 修复 `DrawingDoc.add_dimension()`（改为真正尺寸标注或移除）
4. **export.py** — 修复 `_do_export()`，为不同格式设置正确 SaveAs 选项
5. **bom.py** — 使用标准库 `csv` 模块生成 CSV
6. **constants.py** — `document_type_from_path` 支持 `.step`、`.stl` 等导入格式

### Stage 2 — P1 中风险修复
7. **model.py 拆分** — 将 SketchBuilder/SketchEditor/SketchContour/FeatureTools/DrawingDoc 拆分到独立文件
8. **裸 except Exception 清理** — analysis.py, inspection.py, auto_repair.py, manufacturing.py, snapshot.py, urdf.py, viewer.py, drawing_parser.py, drawing.py, brief.py, benchmark.py, metadata.py, parameters.py, precision.py, repair.py, parts.py
9. **bool_subtract 修复** — 修正 mark 值和 API 调用方式
10. **占位模块标记** — 在未实现方法中添加 `warnings.warn` 或 `NotImplementedError`

### Stage 3 — P2 改进
11. **日志格式化** — f-string 改为 `%` 格式化（所有模块）
12. **FeatureTools 参数重构** — 使用 dataclass 传递参数替代 20+ 位置参数
13. **参数范围验证** — 在 extrude/cut/fillet 等方法中添加数值验证
14. **测试补充** — 为拆分后的新模块添加基本导入测试

## 文件传播
- Stage 1 输出 → Stage 2 输入
- model.py 拆分后，所有引用文件需更新导入

## 验证
- 每阶段结束后运行 `python -c "import solidworks_com; print('OK')"` 验证导入
- 检查 `__init__.py` 的 `__all__` 完整性
