#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Linq;

namespace PCGBike.Editor.Buildings
{
    // 仅界面导航。与 HDA 参数、Undo 和 Cook 生命周期分离。
    internal sealed class StreetBuildingOverrideSelection
    {
        internal int Filter = -1, Target = -1, Face = -1, Row;
        internal void Clear() { Filter = Target = Face = -1; Row = 0; }
        internal void SetFilter(int target) { Filter = target; Target = target; Face = -1; Row = 0; }
        internal void SelectWall(int target, int face) { Filter = Target = target; Face = face; Row = 0; }
        internal void SelectRow(int row, int target) { Row = row; Target = target; Face = -1; }
        internal void TargetEdited(int target) { Filter = -1; Target = target; Face = -1; }
        internal int[] VisibleRows(int count, Func<int, int> target) => Enumerable.Range(1, count)
            .Where(i => Filter < 0 || target(i) == Filter).ToArray();
        private string structure;
        internal void Observe(IEnumerable<int> targets)
        {
            string next = string.Join(",", targets);
            // 删除、移位及 Undo 后无法可靠识别原条目时清除展开项，防止误选下一行。
            if (structure != null && structure != next) Row = 0;
            structure = next;
        }
    }
}
#endif
