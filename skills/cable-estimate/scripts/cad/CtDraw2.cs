// CTDRAW <file.tsv> : lines "group<TAB>layer<TAB>aci<TAB>x,y x,y ..." -> 2D polylines on that layer,
// layer created if missing and put in the top-level layer group "group" (Layer Manager tree).
// CTCLEAR <prefix> : erase model-space entities on layers whose name ends with " (<prefix>...)"  - redo support.
using System.Collections.Generic;
using System.IO;
using IntelliCAD.EditorInput;
using Teigha.Colors;
using Teigha.DatabaseServices;
using Teigha.Geometry;
using Teigha.LayerManager;
using Teigha.Runtime;
using App = IntelliCAD.ApplicationServices.Core.Application;

public class CtDraw2
{
    [CommandMethod("CTDRAW2")]
    public void Draw()
    {
        var doc = App.DocumentManager.MdiActiveDocument; var db = doc.Database; var ed = doc.Editor;
        var r = ed.GetString(new PromptStringOptions("\nFile: ") { AllowSpaces = true });
        if (r.Status != PromptStatus.OK) return;
        int n = 0;
        using (doc.LockDocument())
        using (var tr = db.TransactionManager.StartTransaction())
        {
            var lt = (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForWrite);
            var ms = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForWrite);
            LayerFilterTree tree = db.LayerFilters;
            foreach (var raw in File.ReadAllLines(r.StringResult.Trim('"')))
            {
                var f = raw.Split('\t'); if (f.Length < 4) continue;
                string grp = f[0], lay = f[1]; short aci = short.Parse(f[2]);
                ObjectId lid;
                if (lt.Has(lay)) lid = lt[lay];
                else { var ltr = new LayerTableRecord { Name = lay, Color = Color.FromColorIndex(ColorMethod.ByAci, aci) }; lid = lt.Add(ltr); tr.AddNewlyCreatedDBObject(ltr, true); }
                LayerGroup g = null;
                foreach (LayerFilter lf in tree.Root.NestedFilters) if (lf.Name == grp && lf is LayerGroup) { g = (LayerGroup)lf; break; }
                if (g == null) { g = new LayerGroup { Name = grp }; tree.Root.NestedFilters.Add(g); }
                if (!g.LayerIds.Contains(lid)) g.LayerIds.Add(lid);
                var pl = new Polyline(); int i = 0;
                foreach (var xy in f[3].Split(' '))
                {
                    var c = xy.Split(','); if (c.Length < 2) continue;
                    pl.AddVertexAt(i++, new Point2d(double.Parse(c[0], System.Globalization.CultureInfo.InvariantCulture), double.Parse(c[1], System.Globalization.CultureInfo.InvariantCulture)), 0, 0, 0);
                }
                if (i < 2) continue;
                pl.Layer = lay;
                ms.AppendEntity(pl); tr.AddNewlyCreatedDBObject(pl, true); n++;
            }
            db.LayerFilters = tree;
            tr.Commit();
        }
        ed.WriteMessage("\nCTDRAW " + n);
    }

    // CTCOPYD srcDoc|lay1,lay2|dx,dy : clone model-space entities on those layers from an open drawing, then move by (dx,dy)
    [CommandMethod("CTCOPYD")]
    public void CopyD()
    {
        var dst = App.DocumentManager.MdiActiveDocument;
        var r = dst.Editor.GetString(new PromptStringOptions("src|layers|dx,dy: ") { AllowSpaces = true });
        if (r.Status != PromptStatus.OK) return;
        var parts = r.StringResult.Trim('"').Split('|');
        var layers = new HashSet<string>(parts[1].Split(','));
        var d = parts[2].Split(',');
        var v = new Vector3d(double.Parse(d[0], System.Globalization.CultureInfo.InvariantCulture), double.Parse(d[1], System.Globalization.CultureInfo.InvariantCulture), 0);
        IntelliCAD.ApplicationServices.Document src = null;
        foreach (IntelliCAD.ApplicationServices.Document x in App.DocumentManager) if (Path.GetFileName(x.Name) == parts[0]) src = x;
        if (src == null) { dst.Editor.WriteMessage("CTCOPYD: source not open"); return; }
        var ids = new ObjectIdCollection();
        using (src.LockDocument())
        using (var tr = src.Database.TransactionManager.StartTransaction())
        {
            var ms = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(src.Database), OpenMode.ForRead);
            foreach (ObjectId id in ms) if (layers.Contains(((Entity)tr.GetObject(id, OpenMode.ForRead)).Layer)) ids.Add(id);
            tr.Commit();
        }
        int n = 0;
        using (dst.LockDocument())
        {
            var map = new IdMapping();
            src.Database.WblockCloneObjects(ids, SymbolUtilityServices.GetBlockModelSpaceId(dst.Database), map, DuplicateRecordCloning.Ignore, false);
            using (var tr = dst.Database.TransactionManager.StartTransaction())
            {
                foreach (IdPair p in map)
                    if (p.IsCloned && p.IsPrimary && ids.Contains(p.Key))
                    { var e = tr.GetObject(p.Value, OpenMode.ForWrite) as Entity; if (e != null) { e.TransformBy(Matrix3d.Displacement(v)); n++; } }
                tr.Commit();
            }
        }
        dst.Editor.WriteMessage(" CTCOPYD " + n);
    }

    [CommandMethod("CTCLEARL")]
    public void Clear()
    {
        var doc = App.DocumentManager.MdiActiveDocument; var db = doc.Database; var ed = doc.Editor;
        var r = ed.GetString(new PromptStringOptions("\nLayer suffix: ") { AllowSpaces = true });
        if (r.Status != PromptStatus.OK) return;
        var names = new HashSet<string>(r.StringResult.Trim('"').Split('|')); int n = 0;
        using (doc.LockDocument())
        using (var tr = db.TransactionManager.StartTransaction())
        {
            var ms = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForRead);
            foreach (ObjectId id in ms)
            {
                var e = (Entity)tr.GetObject(id, OpenMode.ForRead);
                if ((e is Polyline || e is Polyline3d) && names.Contains(e.Layer)) { e.UpgradeOpen(); e.Erase(); n++; }
            }
            tr.Commit();
        }
        ed.WriteMessage("\nCTCLEAR " + n);
    }
}
