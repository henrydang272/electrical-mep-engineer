// CTEXPORT <out.tsv> : model-space geometry as "layer<TAB>x1,y1 x2,y2 ..." (lines, polylines; blocks as extents box)
using System.Collections.Generic;
using System.IO;
using IntelliCAD.EditorInput;
using Teigha.DatabaseServices;
using Teigha.Runtime;
using App = IntelliCAD.ApplicationServices.Core.Application;

public class CtExport3
{
    [CommandMethod("CtExport3")]
    public void Run()
    {
        var doc = App.DocumentManager.MdiActiveDocument; var db = doc.Database;
        var r = doc.Editor.GetString(new PromptStringOptions("\nOut: ") { AllowSpaces = true });
        if (r.Status != PromptStatus.OK) return;
        var o = new List<string>();
        using (var tr = db.TransactionManager.StartTransaction())
        {
            var ms = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForRead);
            foreach (ObjectId id in ms)
            {
                var e = (Entity)tr.GetObject(id, OpenMode.ForRead);
                var ln = e as Line; var pl = e as Polyline;
                if (ln != null) o.Add(e.Layer + "\tL\t" + F(ln.StartPoint) + " " + F(ln.EndPoint));
                else if (e is Leader) { var ld = (Leader)e; var s = new List<string>(); for (int i = 0; i < ld.NumVertices; i++) s.Add(F(ld.VertexAt(i))); o.Add(e.Layer + "\tL\t" + string.Join(" ", s) + "\tLEADER"); }
                else if (e is Arc) { var a = (Arc)e; o.Add(e.Layer + "\tL\t" + F(a.StartPoint) + " " + F(a.EndPoint) + "\tARC"); }
                else if (pl != null) { var s = new List<string>(); for (int i = 0; i < pl.NumberOfVertices; i++) s.Add(F(pl.GetPoint3dAt(i))); o.Add(e.Layer + "\tL\t" + string.Join(" ", s)); }
                else if (e is BlockReference || e is MText || e is DBText || e is Circle)
                {
                    try { var x = e.GeometricExtents; var mt = e as MText; var dt = e as DBText; var br = e as BlockReference; o.Add(e.Layer + "\tB\t" + F(x.MinPoint) + " " + F(x.MaxPoint) + "\t" + (mt != null ? mt.Text : dt != null ? dt.TextString : br != null ? br.Name : "")); } catch { }
                }
            }
            tr.Commit();
        }
        File.WriteAllLines(r.StringResult.Trim('"'), o);
        doc.Editor.WriteMessage("\nCTEXPORT " + o.Count);
    }
    static string F(Teigha.Geometry.Point3d p) { return p.X.ToString("F0") + "," + p.Y.ToString("F0"); }
}


