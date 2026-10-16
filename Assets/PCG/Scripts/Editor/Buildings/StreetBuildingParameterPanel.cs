#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using HoudiniEngineUnity;
using PCGBike.Buildings;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    // 自有参数视图直接编辑 HDA；折叠状态和选择不属于生成配置。
    internal sealed class StreetBuildingParameterPanel
    {
        private readonly Dictionary<string, bool> folds = new();
        private static readonly string[] Rhythms = { "随机", "均匀分布", "左右对称", "成组" };
        private static readonly int[] RhythmValues = { 0, 1, 3, 4 };
        private HEU_HoudiniAsset asset;
        private StreetBuildingAuthoring author;
        private StreetBuildingGenerationPolicy.Data policy;
        private HEU_HoudiniAsset policyAsset;
        private string policyHash;
        private int selectedTarget = -1, selectedFace = -1, selectedOverride;
        private readonly StreetBuildingOverrideSelection navigation = new();
        private List<StreetBuildingFacadeDiagram.Segment> segments = new();

        internal static void Edit(HEU_HoudiniAsset a, string name, double value, bool floating = false)
        {
            StreetBuildingParameterTransaction.Run(a, "修改 StreetBuilding 参数", () =>
            {
                if (floating) StreetBuildingInstanceParameters.SetFloat(a, name, (float)value);
                else StreetBuildingInstanceParameters.SetInt(a, name, (int)value);
                if (name == "l_notch_width_cells" || name == "l_notch_depth_cells") StreetBuildingInstanceParameters.SetInt(a, "l_notch_units", 1);
            }, StreetBuildingParameterTransaction.IsStructure(name));
        }

        internal void Draw(StreetBuildingAuthoring owner)
        {
            author = owner; asset = owner.GetComponent<HEU_HoudiniAssetRoot>()?.HoudiniAsset;
            var state = StreetBuildingPanelState.Get(owner);
            EditorGUILayout.Space(5);
            EditorGUILayout.LabelField("生成状态", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox(StreetBuildingPanelState.Status(state), string.IsNullOrEmpty(state.Error) ? MessageType.Info : MessageType.Error);
            if (!string.IsNullOrEmpty(state.Error)) EditorGUILayout.HelpBox(state.Error, MessageType.Error);
            if (!state.Valid && !state.Cooking && !state.Requested && asset != null)
            {
                EditorGUILayout.HelpBox("实例未连接时参数暂不可编辑；已保存参数与上次场景结果保留。恢复连接后，再点击“生成”更新结果。", MessageType.Info);
                if (GUILayout.Button("恢复实例连接（保留参数和上次结果）"))
                    try { StreetBuildingSessionRecovery.Restore(owner); }
                    catch (Exception exception) { state.Error = "恢复实例失败：" + (exception.InnerException?.Message ?? exception.Message); }
            }
            if (state.Result == null && string.IsNullOrEmpty(owner.LastCookDiagnostic)) EditorGUILayout.LabelField("尚未生成", EditorStyles.miniLabel);
            if (state.Result != null)
            {
                EditorGUILayout.LabelField("结果版本", state.Result.inputHash.Substring(0, 8));
                var changes = StreetBuildingChangeSummary.Build(state.Result, state.Current, owner.ResolveStyle()?.CellWidth ?? 0);
                if (changes.Count > 0)
                {
                    foreach (var group in changes.Where(r => !r.Inactive).GroupBy(r => r.Area))
                        EditorGUILayout.LabelField(group.Key, string.Join("\n", group.Take(2).Select(r => r.ToString()))
                            + (group.Count() > 2 ? $"\n另有 {group.Count() - 2} 项，展开查看" : ""), EditorStyles.wordWrappedMiniLabel);
                    if (Fold("changes", "展开详细修改（" + changes.Count + "项）", false))
                        foreach (var row in changes)
                            EditorGUILayout.LabelField(row.ToString(), EditorStyles.wordWrappedMiniLabel);
                }
            }
            bool policyAvailable = asset != null && StreetBuildingInstanceParameters.Exists(asset, StreetBuildingGenerationPolicy.Parameter)
                && StreetBuildingInstanceParameters.Exists(asset, StreetBuildingGenerationPolicy.SequenceParameter);
            using (new EditorGUI.DisabledScope(!state.Valid || state.Cooking || state.Requested || owner.ResolveStyle() == null || !policyAvailable))
                if (GUILayout.Button(state.Cooking ? "生成中…" : "生成"))
                {
                    try { Generate(asset); }
                    catch (Exception exception) { StreetBuildingPanelState.Fail(owner, exception.Message); }
                }
            if (asset == null || asset.Parameters == null) { EditorGUILayout.HelpBox("缺少 HDA 实例，生成参数不可编辑。", MessageType.Info); return; }
            if (!policyAvailable)
            {
                EditorGUILayout.HelpBox("当前实例定义尚未包含区间／候选配置，请更新 HDA definition 并 Rebuild 实例。", MessageType.Warning);
                return;
            }
            if (policy == null || policyAsset != asset || policyHash != state.CurrentHash)
            {
                policy = StreetBuildingGenerationPolicy.WithDefaults(asset);
                policyAsset = asset; policyHash = state.CurrentHash;
            }
            using (new EditorGUI.DisabledScope(!state.Valid || state.Cooking || state.Requested))
            {
                if (Fold("massing", "建筑体块")) DrawMassing();
                if (Fold("ground", "首层门窗")) DrawGround(state);
                if (Fold("upper", "标准层门窗"))
                {
                    Quantity("window_count", "window_count_min", "window_count_max", I("facade_layout_mode"), "窗模块（每层每物理立面）");
                    Rhythm("facade_rhythm", "排列方式");
                }
                if (Fold("roof", "屋顶与线脚")) DrawRoof();
                if (Fold("attachments", "附件", false)) DrawAttachments(state);
                if (Fold("local", "局部覆盖")) DrawOverrides(state);
                if (Fold("seed", "种子与调试", false))
                { Int("variation_seed", "变化种子（用途与素材）"); Int("layout_seed", "布局种子（门位与布局）"); Toggle("debug_metadata_enabled", "调试元数据"); }
            }
            if (state.Result != null && Fold("diagnostics", "上次成功生成诊断", false))
                EditorGUILayout.HelpBox(state.Result.summary, MessageType.Info);
        }

        internal static bool Generate(HEU_HoudiniAsset a)
        {
            if (!StreetBuildingInstanceParameters.Exists(a, StreetBuildingGenerationPolicy.Parameter)
                || !StreetBuildingInstanceParameters.Exists(a, StreetBuildingGenerationPolicy.SequenceParameter))
                throw new InvalidOperationException("当前 HDA 定义缺少区间生成参数；请更新并 Rebuild 实例。");
            var owner = a.GetComponentInParent<StreetBuildingAuthoring>();
            var state = StreetBuildingPanelState.Get(owner);
            if (state.Cooking || state.Requested) return false;
            a.AutoCookOnParameterChange = false; a.SessionSyncAutoCook = false;
            StreetBuildingRecook.Attach();
            StreetBuildingRecook.ArmGeneration(a);
            bool accepted;
            try { accepted = a.RequestCook(true, true, true, true); }
            catch { StreetBuildingRecook.DisarmGeneration(a); throw; }
            if (!accepted) StreetBuildingRecook.DisarmGeneration(a);
            if (accepted) state.Requested = true;
            if (!accepted) StreetBuildingPanelState.Fail(owner, "生成请求未被接受");
            return accepted;
        }

        private void DrawMassing()
        {
            var input = asset.GetInputNodeByIndex(0);
            bool external = I("site_source_auto", 1) != 0 ? input != null && input.GetConnectedInputCount() > 0 : I("site_source") == 1;
            EditorGUILayout.LabelField("地块来源", external ? "输入地块；尺寸由地块决定" : "独栋；使用本实例尺寸");
            using (new EditorGUI.DisabledScope(external))
            { Dimension("building_width", "宽度"); Dimension("building_depth", "进深"); }
            Popup("massing_shape", "体块形状", new[] { "矩形", "L 形" });
            if (CandidateIncludes("massing_shape", 1))
            {
                Int("l_notch_width_cells", "缺口宽度（格）"); Int("l_notch_depth_cells", "缺口进深（格）");
                Popup("l_notch_side", "缺口方向", new[] { "后左", "后右", "前左", "前右" });
            }
            Int("floor_count", "楼层数（1～12）");
            Popup("rear_facade_mode", "后立面", new[] { "关闭", "完整立面" }, new[] { 0, 2 });
        }
        internal static float NearestDimension(float metres, float cellWidth, int notchCells = 0)
            // HDA 会将缺口有效格数限制到尺寸格数 - 1；宽/深合法下界均为两格。
            => Mathf.Max(2, Mathf.RoundToInt(metres / cellWidth)) * cellWidth;
        internal static void EditDimensionCells(StreetBuildingAuthoring owner, string name, float cells)
        {
            float cellWidth = owner.ResolveStyle()?.CellWidth ?? 0;
            float metres = cells * cellWidth;
            if (cellWidth <= 0 || float.IsNaN(metres) || float.IsInfinity(metres))
                throw new InvalidOperationException("素材格宽或输入格数无效。");
            // 仅在用户编辑时换算；沿用 HDA 米制字段，避免第二套配置及素材切换隐式改写。
            Edit(owner.GetComponent<HEU_HoudiniAssetRoot>()?.HoudiniAsset, name, metres, true);
        }
        private void Dimension(string name, string label)
        {
            var cached = asset.Parameters.GetParameter(name);
            var current = StreetBuildingPanelState.Get(author);
            bool known = cached?._floatValues?.Length > 0 || current.Valid && current.Current.Any(r => r.name == name);
            if (!known)
            { EditorGUILayout.LabelField(label + "（格）", "尚未读取；请恢复实例连接"); return; }
            float width = author.ResolveStyle()?.CellWidth ?? 0;
            if (width <= 0 || float.IsNaN(width) || float.IsInfinity(width))
            { EditorGUILayout.LabelField(label + "（格）", "格宽不可用；请指定有效素材规格"); return; }
            float cells = Mathf.Max(2, Mathf.RoundToInt(F(name) / width));
            var info = asset.Parameters.GetParameter(name)?._parmInfo;
            int upper = info.HasValue && info.Value.hasMax ? Mathf.Max(2, Mathf.FloorToInt(info.Value.max / width)) : 50;
            DrawRange(name, label + "（格）", cells, cells, 2, upper, true);
        }
        private void DrawGround(StreetBuildingPanelState.State state)
        {
            Popup("ground_floor_use", "首层用途", new[] { "住宅", "商业" }, new[] { 1, 2 }); int use = I("ground_floor_use");
            if (CandidateIncludes("ground_floor_use", 1) && CandidateIncludes("ground_floor_use", 2)) EditorGUILayout.LabelField("本次实际用途", state.Result == null ? "尚无可确认的结果" : (state.Result.actualUse == 2 ? "商业" : "住宅")
                + (state.CurrentHash == state.Result.inputHash ? "" : "（上次成功结果）"));
            if (CandidateIncludes("ground_floor_use", 1) && Fold("residential", "住宅配置", state.Result?.actualUse != 2)) Toggle("residential_door_enabled", "生成住宅入户门");
            if (CandidateIncludes("ground_floor_use", 2) && Fold("commercial", "商业配置", state.Result?.actualUse == 2))
            {
                Quantity("entrance_count", "entrance_count_min", "entrance_count_max", I("ground_quantity_mode"), "商业门（整栋首层）");
                Popup("shopfront_control", "橱窗控制", new[] { "模块数量", "占格比例" });
                ShopfrontFaces();
                if (CandidateIncludes("shopfront_control", 0)) Quantity("shopfront_count", "shopfront_count_min", "shopfront_count_max", I("shopfront_quantity_mode"), "橱窗（每个选中启用立面）");
                if (CandidateIncludes("shopfront_control", 1)) Float("shopfront_ratio", "占格比例（扣除门后可用格；0～1）");
            }
            Rhythm("ground_rhythm", "首层排列方式");
        }
        private void DrawRoof()
        {
            Toggle("roof_enabled", "生成屋顶"); Toggle("parapet_enabled", "生成女儿墙");
            if (CandidateIncludes("parapet_enabled", 1)) Float("parapet_height", "女儿墙高度（米）");
            Toggle("architectural_trim_enabled", "生成线脚"); Toggle("corner_building", "街角建筑");
            if (CandidateIncludes("corner_building", 1)) Popup("corner_street_side", "首层临街侧面", new[] { "左", "右", "两侧" });
        }
        private void DrawAttachments(StreetBuildingPanelState.State state)
        {
            Toggle("attachments_enabled", "生成附件");
            if (!CandidateIncludes("attachments_enabled", 1))
            {
                EditorGUILayout.LabelField("附件关闭；关联编辑项已收起。本次请求不生成附件。", EditorStyles.wordWrappedMiniLabel);
                if (state.Result != null && Fold("disabledAttachmentDiagnostics", "上次成功结果：挂点、上限与关闭原因", false))
                    EditorGUILayout.HelpBox("以下为上次成功结果，当前输入尚未生成时不代表当前容量。\n" + state.AttachmentDiagnostics.Format(), MessageType.None);
                return;
            }
            Float("attachment_global_density", "全局密度（0～1）");
            Popup("ground_attachment_placement", "雨棚 / 招牌挂点", new[] { "网格随机", "跟随实际门窗" });
            var names = new[] { "awning", "sign", "fire_escape", "wall_ac", "roof_props" };
            var labels = new[] { "雨棚", "招牌", "消防梯", "墙面空调", "屋顶附件" };
            for (int i = 0; i < names.Length; i++) if (Fold(names[i], labels[i], false))
            {
                Float(names[i] + "_density", "采样密度（0～1）"); Int(names[i] + "_max_count", "请求数量上限");
                if (state.Result == null) EditorGUILayout.LabelField("挂点与有效上限：等待生成");
                else
                {
                    if (state.AttachmentDiagnostics.Error != null) EditorGUILayout.HelpBox(state.AttachmentDiagnostics.Error, MessageType.Info);
                    foreach (var row in state.AttachmentDiagnostics.Rows.Where(r => r.Kind == i))
                        EditorGUILayout.HelpBox("上次成功结果：" + row.Text, MessageType.None);
                }
            }
        }
        private static string AttachmentSource(string source) => source == "instance" ? "基础参数"
            : source.StartsWith("attachment_override:", StringComparison.Ordinal) ? "附件覆盖第" + source.Substring("attachment_override:".Length) + "条"
            : source.StartsWith("parcel:", StringComparison.Ordinal) ? "地块覆盖第" + source.Substring("parcel:".Length) + "条" : source;
        internal static string AttachmentReasons(string value) => StreetBuildingAttachmentDiagnostics.ReasonLabel(value);

        private void DrawOverrides(StreetBuildingPanelState.State state)
        {
            int count = I("facade_overrides");
            navigation.Observe(Enumerable.Range(1, count).Select(i => I("facade_override_target" + i)));
            if (selectedOverride > 0 && navigation.Row == 0) selectedOverride = 0;
            using (new EditorGUILayout.HorizontalScope())
            {
                int filter = EditorGUILayout.Popup("显示覆盖", navigation.Filter + 1,
                    new[] { "全部", "正面", "次正面", "侧面（左、右）", "背面" }) - 1;
                if (filter != navigation.Filter) { navigation.SetFilter(filter); SyncNavigation(); }
                if (GUILayout.Button("全部覆盖 / 清除选择", GUILayout.MaxWidth(160))) { navigation.Clear(); SyncNavigation(); }
            }
            bool reliable = state.Result != null;
            segments = reliable ? StreetBuildingFacadeDiagram.Parse(state.Result.facades) : StreetBuildingFacadeDiagram.Preview(F("building_width", 12), F("building_depth", 10), I("massing_shape"),
                I("l_notch_width_cells", 2) * (author.ResolveStyle()?.CellWidth ?? 2), I("l_notch_depth_cells", 2) * (author.ResolveStyle()?.CellWidth ?? 2), I("l_notch_side"));
            if (Fold("diagram", "立面小示意图"))
            {
                EditorGUILayout.LabelField(reliable ? "上次成功结果 " + state.Result.inputHash.Substring(0, 8) : "参数示意；尚无真实墙段映射", EditorStyles.miniLabel);
                int targetBefore = selectedTarget, faceBefore = selectedFace;
                StreetBuildingFacadeDiagram.Draw(GUILayoutUtility.GetRect(180, 250, GUILayout.ExpandWidth(true)), segments, ref selectedTarget, ref selectedFace);
                if (selectedTarget != targetBefore || selectedFace != faceBefore) { navigation.SelectWall(selectedTarget, selectedFace); SyncNavigation(); }
                EditorGUILayout.LabelField("绿色：覆盖范围；橙色：同物理立面共享额度", EditorStyles.wordWrappedMiniLabel);
                if (selectedTarget >= 0) EditorGUILayout.LabelField("已选择", StreetBuildingFacadeDiagram.Targets[selectedTarget]);
            }
            var matches = navigation.VisibleRows(count, i => I("facade_override_target" + i));
            if (matches.Length == 0) EditorGUILayout.LabelField(count == 0 ? "未设置局部覆盖，使用基础参数" : "此范围未设置覆盖；可切换“全部”查看其它条目。", EditorStyles.wordWrappedMiniLabel);
            foreach (int row in matches)
            {
                int target = I("facade_override_target" + row), start = I("facade_override_floor_start" + row), end = I("facade_override_floor_end" + row);
                using (new EditorGUILayout.VerticalScope(EditorStyles.helpBox))
                {
                    if (GUILayout.Button($"覆盖 {row} · {StreetBuildingFacadeDiagram.Targets[Mathf.Clamp(target, 0, 3)]} · 第{start}～{end}层"))
                    { navigation.SelectRow(row, target); SyncNavigation(); }
                    if (selectedOverride != row) continue;
                    Popup("facade_override_target" + row, "目标范围", StreetBuildingFacadeDiagram.Targets);
                    if (I("facade_override_target" + row) != target)
                    { target = I("facade_override_target" + row); navigation.TargetEdited(target); navigation.Observe(Enumerable.Range(1, count).Select(i => I("facade_override_target" + i))); navigation.SelectRow(row, target); SyncNavigation(); }
                    ScopeInt("facade_override_floor_start" + row, "起始楼层"); ScopeInt("facade_override_floor_end" + row, "结束楼层");
                    int mode = I("facade_override_layout_mode" + row);
                    int scope = EditorGUILayout.Popup("数量覆盖", mode == 0 ? 0 : 1, new[] { "继承基础", "使用下方区间" });
                    if (scope != (mode == 0 ? 0 : 1)) Edit(asset, "facade_override_layout_mode" + row, scope == 0 ? 0 : 2);
                    mode = I("facade_override_layout_mode" + row);
                    Rhythm("facade_override_rhythm" + row, "排列方式");
                    if (start <= 1 && end >= 1 && I("ground_floor_use") != 1)
                        Quantity("facade_override_shopfront_" + row, "facade_override_shopfront_min" + row, "facade_override_shopfront_max" + row, mode == 1 ? 1 : 0, "首层橱窗模块");
                    if (end >= 2) Quantity("facade_override_window_" + row, "facade_override_window_min" + row, "facade_override_window_max" + row, mode == 1 ? 1 : 0, "标准层窗模块");
                    string counts = "";
                    if (start <= 1 && end >= 1 && CandidateIncludes("ground_floor_use", 2)) counts += "橱窗 " + QuantityText("facade_override_shopfront_" + row) + " 模块；";
                    if (end >= 2) counts += "窗 " + QuantityText("facade_override_window_" + row) + " 模块／层／物理立面；";
                    int rhythm = Array.IndexOf(RhythmValues, I("facade_override_rhythm" + row));
                    EditorGUILayout.LabelField("覆盖摘要", $"{StreetBuildingFacadeDiagram.Targets[Mathf.Clamp(target, 0, 3)]}；第{start}～{end}层；{counts}{Rhythms[Mathf.Max(0, rhythm)]}；{(mode == 0 ? "继承基础" : "使用覆盖区间")}", EditorStyles.wordWrappedMiniLabel);
                    if (mode == 0) EditorGUILayout.LabelField("自动模式说明", AutoSummary(row, start, end), EditorStyles.wordWrappedMiniLabel);
                    if (start < 1 || end < start || start > I("floor_count")) EditorGUILayout.HelpBox("楼层范围无效或超出建筑；请求值已保留，请主动调整。", MessageType.Warning);
                    else if (reliable && !segments.Any(s => s.Target == target))
                    {
                        string reason = target == 3 ? "上次结果没有可用后立面；后立面关闭时不参与覆盖。"
                            : target == 1 ? "上次结果没有次正面；矩形及后缺口 L 形不具有次正面。"
                            : "上次结果没有该方向的可用墙段。";
                        EditorGUILayout.HelpBox(reason + (state.CurrentHash != state.Result.inputHash ? " 当前参数已修改，本提示对应上次成功结果。" : ""), MessageType.Info);
                    }
                    if (GUILayout.Button("删除此覆盖")) { RemoveRow("facade_overrides", row); navigation.Clear(); SyncNavigation(); break; }
                }
            }
            if (GUILayout.Button("新增立面覆盖")) { Edit(asset, "facade_overrides", count + 1); navigation.Clear(); navigation.Observe(Enumerable.Range(1, count + 1).Select(i => I("facade_override_target" + i))); navigation.SelectRow(count + 1, I("facade_override_target" + (count + 1))); SyncNavigation(); }
            if (Fold("attachmentOverrides", "附件覆盖", false)) DrawAttachmentOverrides();
        }
        private void SyncNavigation() { selectedTarget = navigation.Target; selectedFace = navigation.Face; selectedOverride = navigation.Row; }
        private string AutoSummary(int row, int start, int end)
        {
            bool ground = start <= 1 && end >= 1 && CandidateIncludes("ground_floor_use", 2);
            bool upper = Mathf.Max(2, start) <= Mathf.Min(end, I("floor_count"));
            bool active = ground && I("facade_override_shopfront_min" + row) != 0 || upper && I("facade_override_window_min" + row) != 0;
            bool rhythm = I("facade_override_rhythm" + row) != 0;
            return (CandidateIncludes("ground_floor_use", 1) && CandidateIncludes("ground_floor_use", 2) ? "输入预计（随机实际用途以生成诊断为准）：" : "输入判定：")
                + (active ? "本条覆盖生效。" : rhythm ? "排列参数激活本条覆盖；适用数量按本条输入。" : "继承基础参数。")
                + "继承状态下数量区间不参与当前生成。";
        }
        private void DrawAttachmentOverrides()
        {
            int count = I("attachment_overrides");
            for (int row = 1; row <= count; row++) if (Fold("attachmentRow" + row, "附件覆盖 " + row, false))
            {
                Popup("attachment_override_kind" + row, "附件类型", new[] { "雨棚", "招牌", "消防梯", "墙面空调", "屋顶附件" });
                Float("attachment_override_density" + row, "密度（0～1）"); Int("attachment_override_max_count" + row, "数量上限");
                foreach (var pair in new[] { ("front", "正面"), ("secondary_front", "次正面"), ("side", "侧面（左、右）"), ("rear", "背面") })
                    Toggle("attachment_override_" + pair.Item1 + row, pair.Item2);
                ScopeInt("attachment_override_floor_start" + row, "起始楼层"); ScopeInt("attachment_override_floor_end" + row, "结束楼层");
                var targets = new[] { ("front", "正面"), ("secondary_front", "次正面"), ("side", "侧面（左、右）"), ("rear", "背面") }
                    .Where(p => I("attachment_override_" + p.Item1 + row) != 0).Select(p => p.Item2);
                int start = I("attachment_override_floor_start" + row), end = I("attachment_override_floor_end" + row);
                EditorGUILayout.LabelField("覆盖摘要", $"{string.Join("、", targets)}；第{start}～{end}层；密度 {F("attachment_override_density" + row):0.###}；上限 {I("attachment_override_max_count" + row)}", EditorStyles.wordWrappedMiniLabel);
                if (start < 1 || end < start || start > I("floor_count") + 1) EditorGUILayout.HelpBox("楼层范围无效；请求值已保留。", MessageType.Warning);
                if (GUILayout.Button("删除附件覆盖")) { RemoveRow("attachment_overrides", row); break; }
            }
            if (GUILayout.Button("新增附件覆盖")) Edit(asset, "attachment_overrides", count + 1);
        }
        private void RemoveRow(string multi, int row)
        {
            StreetBuildingParameterTransaction.Run(asset, "删除 StreetBuilding 覆盖", () =>
            {
                var session = asset.GetAssetSession(false);
                if (!session.GetParmIDFromName(asset.AssetID, multi, out int id) || !session.RemoveMultiParmInstance(asset.AssetID, id, row))
                    throw new InvalidOperationException("删除覆盖失败");
                StreetBuildingGenerationPolicy.ShiftAfterRowRemoval(asset, multi, row);
            }, true);
        }

        private string QuantityText(string key)
        {
            var rule = StreetBuildingGenerationPolicy.Find(policy, key);
            return rule == null ? "使用当前实例值" : Mathf.RoundToInt(rule.min) + (rule.min == rule.max ? "" : "～" + Mathf.RoundToInt(rule.max));
        }

        private void Quantity(string key, string min, string max, int mode, string label)
        {
            int low = key == "entrance_count" && mode == 0 ? I(max) : key == "shopfront_count" && mode == 0 ? I(key) : I(min);
            int high = mode == 1 ? I(max) : low;
            var p = asset.Parameters.GetParameter(max)?._parmInfo;
            int boundMin = p.HasValue && p.Value.hasMin ? Mathf.RoundToInt(p.Value.min) : 0;
            int boundMax = p.HasValue && p.Value.hasMax ? Mathf.RoundToInt(p.Value.max) : 64;
            DrawRange(key, label, low, high, boundMin, boundMax, true);
        }
        // 重绘只读 HEU 缓存或节流快照；隐藏字段也不在重绘中逐项请求 HAPI。
        private int I(string name, int fallback = 0)
        {
            var p = asset?.Parameters?.GetParameter(name);
            if (p?._intValues?.Length > 0) return p._intValues[0];
            if (p != null && p._parmInfo.type == HAPI_ParmType.HAPI_PARMTYPE_TOGGLE) return p._toggle ? 1 : 0;
            if (p != null && p._parmInfo.type == HAPI_ParmType.HAPI_PARMTYPE_MULTIPARMLIST) return p._parmInfo.instanceCount;
            var row = StreetBuildingPanelState.Get(author).Current.Find(r => r.name == name);
            return row != null && int.TryParse(row.value, NumberStyles.Integer, CultureInfo.InvariantCulture, out int value) ? value : fallback;
        }
        private float F(string name, float fallback = 0)
        {
            var p = asset?.Parameters?.GetParameter(name);
            if (p?._floatValues?.Length > 0) return p._floatValues[0];
            var row = StreetBuildingPanelState.Get(author).Current.Find(r => r.name == name);
            return row != null && float.TryParse(row.value, NumberStyles.Float, CultureInfo.InvariantCulture, out float value) ? value : fallback;
        }
        private void ScopeInt(string name, string label) { int old = I(name), value = EditorGUILayout.IntField(label, old); if (old != value) Edit(asset, name, value); }
        private void Int(string name, string label)
        {
            var p = asset.Parameters.GetParameter(name)?._parmInfo;
            int lower = name == "layout_seed" ? -1 : p.HasValue && p.Value.hasMin ? Mathf.RoundToInt(p.Value.min) : 0;
            int upper = name == "layout_seed" ? 999999 : p.HasValue && p.Value.hasMax ? Mathf.RoundToInt(p.Value.max) : Mathf.Max(20, I(name) + 20);
            DrawRange(name, label, I(name), I(name), lower, upper, true);
        }
        private void Float(string name, string label)
        {
            var p = asset.Parameters.GetParameter(name)?._parmInfo;
            float lower = p.HasValue && p.Value.hasMin ? p.Value.min : 0;
            float upper = p.HasValue && p.Value.hasMax ? p.Value.max : Mathf.Max(1, F(name) * 2);
            DrawRange(name, label, F(name), F(name), lower, upper, false);
        }
        private void DrawRange(string name, string label, float fallbackMin, float fallbackMax, float lower, float upper, bool integer)
        {
            var rule = StreetBuildingGenerationPolicy.Number(policy, name, fallbackMin, fallbackMax);
            float min = rule.min, max = rule.max;
            EditorGUILayout.LabelField(label);
            using (new EditorGUILayout.HorizontalScope())
            {
                GUILayout.Label(integer ? Mathf.RoundToInt(min).ToString() : min.ToString("0.###", CultureInfo.InvariantCulture), GUILayout.Width(45));
                EditorGUI.BeginChangeCheck();
                EditorGUILayout.MinMaxSlider(ref min, ref max, lower, upper);
                if (EditorGUI.EndChangeCheck())
                {
                    min = integer ? Mathf.Round(min) : min;
                    max = integer ? Mathf.Round(max) : max;
                    min = Mathf.Clamp(min, lower, upper);
                    max = Mathf.Clamp(max, min, upper);
                    SaveRule(new StreetBuildingGenerationPolicy.Rule { name = name, kind = rule.kind == "quantity" ? "quantity" : "number", min = min, max = max });
                }
                GUILayout.Label(integer ? Mathf.RoundToInt(max).ToString() : max.ToString("0.###", CultureInfo.InvariantCulture), GUILayout.Width(45));
            }
            string status = min == max ? "固定" : "随机范围";
            if (StreetBuildingPanelState.Get(author).Result != null)
            {
                if (rule.kind == "quantity") status += "；实际模块数见生成诊断";
                else status += "；上次实际 " + (name == "building_width" || name == "building_depth"
                    ? (F(name) / (author.ResolveStyle()?.CellWidth ?? 1)).ToString("0", CultureInfo.InvariantCulture)
                    : integer ? I(name).ToString(CultureInfo.InvariantCulture) : F(name).ToString("0.###", CultureInfo.InvariantCulture));
            }
            EditorGUILayout.LabelField(status, EditorStyles.miniLabel);
        }
        private void SaveRule(StreetBuildingGenerationPolicy.Rule rule)
        {
            StreetBuildingGenerationPolicy.Set(asset, rule);
            policy = StreetBuildingGenerationPolicy.WithDefaults(asset);
            policyHash = StreetBuildingPanelState.Get(author).CurrentHash;
        }
        private void Toggle(string name, string label) => Popup(name, label, new[] { "关", "开" });
        private void Popup(string name, string label, string[] choices, int[] values = null)
        {
            int[] known = StreetBuildingGenerationPolicy.Values(name);
            if (known != null)
            {
                values ??= known;
                int current = Array.IndexOf(values, I(name));
                int fallback = name == "ground_floor_use" && I(name) == 0 ? 3 : 1 << Mathf.Max(0, current);
                int mask = StreetBuildingGenerationPolicy.Choice(policy, name, fallback).mask & ((1 << choices.Length) - 1);
                if (mask == 0) mask = fallback;
                string selected = string.Join("、", Enumerable.Range(0, choices.Length).Where(i => (mask & (1 << i)) != 0).Select(i => choices[i]));
                Rect rect = EditorGUILayout.GetControlRect();
                Rect dropdown = EditorGUI.PrefixLabel(rect, new GUIContent(label));
                if (EditorGUI.DropdownButton(dropdown, new GUIContent(selected), FocusType.Passive, EditorStyles.popup))
                {
                    var menu = new GenericMenu();
                    for (int i = 0; i < choices.Length; i++)
                    {
                        int bit = 1 << i;
                        menu.AddItem(new GUIContent(choices[i]), (mask & bit) != 0, () =>
                        {
                            int currentMask = StreetBuildingGenerationPolicy.Choice(StreetBuildingGenerationPolicy.WithDefaults(asset), name, fallback).mask;
                            int next = currentMask ^ bit;
                            if (next == 0) return;
                            SaveRule(new StreetBuildingGenerationPolicy.Rule { name = name, kind = "choice", mask = next });
                        });
                    }
                    menu.DropDown(dropdown);
                }
                string status = (mask & (mask - 1)) == 0 ? "固定" : "随机单项";
                int actual = Array.IndexOf(values, I(name));
                if (actual >= 0 && StreetBuildingPanelState.Get(author).Result != null) status += "；上次实际 " + choices[actual];
                EditorGUILayout.LabelField(status, EditorStyles.miniLabel);
                return;
            }
            int old = I(name), index = values == null ? old : Array.IndexOf(values, old);
            int value = EditorGUILayout.Popup(label, Mathf.Clamp(index, 0, choices.Length - 1), choices);
            if (value != index) Edit(asset, name, values == null ? value : values[value]);
        }
        private bool CandidateIncludes(string name, int value)
        {
            int[] values = StreetBuildingGenerationPolicy.Values(name);
            if (values == null) return I(name) == value;
            int index = Array.IndexOf(values, value);
            int current = Array.IndexOf(values, I(name));
            int fallback = name == "ground_floor_use" && I(name) == 0 ? 3 : 1 << Mathf.Max(0, current);
            return index >= 0 && (StreetBuildingGenerationPolicy.Choice(policy, name, fallback).mask & (1 << index)) != 0;
        }
        private void ShopfrontFaces()
        {
            const string key = StreetBuildingGenerationPolicy.FacesKey;
            string[] labels = { "正面", "左", "右", "后" };
            int fallback = 0;
            for (int i = 0; i < 4; i++) if (I("shopfront_face_" + i) != 0) fallback |= 1 << i;
            if (fallback == 0) fallback = 1;
            int mask = StreetBuildingGenerationPolicy.Find(policy, key)?.mask ?? fallback;
            string selected = string.Join("、", Enumerable.Range(0, 4).Where(i => (mask & (1 << i)) != 0).Select(i => labels[i]));
            Rect rect = EditorGUILayout.GetControlRect();
            Rect dropdown = EditorGUI.PrefixLabel(rect, new GUIContent("橱窗立面"));
            if (EditorGUI.DropdownButton(dropdown, new GUIContent(selected), FocusType.Passive, EditorStyles.popup))
            {
                var menu = new GenericMenu();
                for (int i = 0; i < 4; i++)
                {
                    int bit = 1 << i;
                    menu.AddItem(new GUIContent(labels[i]), (mask & bit) != 0, () =>
                    {
                        int current = StreetBuildingGenerationPolicy.Find(StreetBuildingGenerationPolicy.WithDefaults(asset), key)?.mask ?? fallback;
                        int next = current ^ bit;
                        if (next != 0) SaveRule(new StreetBuildingGenerationPolicy.Rule { name = key, kind = "faces", mask = next });
                    });
                }
                menu.DropDown(dropdown);
            }
            string status = (mask & (mask - 1)) == 0 ? "固定立面" : "随机非空立面组合";
            if (StreetBuildingPanelState.Get(author).Result != null)
            {
                int actual = 0;
                for (int i = 0; i < 4; i++) if (I("shopfront_face_" + i) != 0) actual |= 1 << i;
                status += "；上次实际 " + string.Join("、", Enumerable.Range(0, 4).Where(i => (actual & (1 << i)) != 0).Select(i => labels[i]));
            }
            EditorGUILayout.LabelField(status, EditorStyles.miniLabel);
        }
        private void Rhythm(string name, string label) => Popup(name, label, Rhythms, RhythmValues);
        private bool Fold(string id, string label, bool initial = true)
        { bool value = folds.TryGetValue(id, out var old) ? old : initial; folds[id] = EditorGUILayout.Foldout(value, label, true, EditorStyles.foldoutHeader); return folds[id]; }
        private static string Area(string name) => name.StartsWith("__material") ? "素材规格" : name.StartsWith("__input") ? "输入地块与引导"
            : name.StartsWith("facade_override") || name.StartsWith("attachment_override") ? "局部覆盖"
            : name.StartsWith("building_") || name.StartsWith("l_notch") || name == "massing_shape" || name == "floor_count" || name == "rear_facade_mode" ? "建筑体块"
            : name.StartsWith("window_") || name.StartsWith("facade_") ? "标准层门窗"
            : name.Contains("density") || name.Contains("max_count") || name.StartsWith("attachment") ? "附件"
            : name.StartsWith("roof") || name.StartsWith("parapet") || name.Contains("trim") ? "屋顶与线脚"
            : name.Contains("seed") ? "种子" : "首层门窗";
    }
}
#endif
