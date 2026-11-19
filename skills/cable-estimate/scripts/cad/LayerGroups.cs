// progeCAD .NET plugin: command LAYGROUPS <spec.txt>
// spec lines: GROUP<TAB>LAYER<TAB>ACI color   (# = comment). Creates missing layers and
// puts each layer in a top-level layer group filter named GROUP (Layer Manager tree).
using System.IO;
using IntelliCAD.ApplicationServices;
using Teigha.DatabaseServices;
using Teigha.LayerManager;
using Teigha.Runtime;
using Teigha.Colors;

public class LayerGroupsCmd
{
    [CommandMethod("LAYGROUPS")]
    public void Run()
    {
        var doc = IntelliCAD.ApplicationServices.Core.Application.DocumentManager.MdiActiveDocument;
        var ed = doc.Editor;
        var pr = ed.GetString(new IntelliCAD.EditorInput.PromptStringOptions("\nSpec file: ") { AllowSpaces = true });
        if (pr.Status != IntelliCAD.EditorInput.PromptStatus.OK || !File.Exists(pr.StringResult.Trim('"')))
        { ed.WriteMessage("\nLAYGROUPS: spec file not found."); return; }
        var db = doc.Database;
        int nLay = 0, nGrp = 0;
        using (doc.LockDocument())
        using (var tr = db.TransactionManager.StartTransaction())
        {
            var lt = (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForWrite);
            LayerFilterTree tree = db.LayerFilters;
            foreach (var raw in File.ReadAllLines(pr.StringResult.Trim('"')))
            {
                var line = raw.Trim();
                if (line.Length == 0 || line.StartsWith("#")) continue;
                var f = line.Split('\t');
                string grp = f[0], lay = f[1];
                short aci = f.Length > 2 ? short.Parse(f[2]) : (short)7;
                ObjectId lid;
                if (lt.Has(lay)) lid = lt[lay];
                else
                {
                    var ltr = new LayerTableRecord { Name = lay, Color = Color.FromColorIndex(ColorMethod.ByAci, aci) };
                    lid = lt.Add(ltr); tr.AddNewlyCreatedDBObject(ltr, true); nLay++;
                }
                LayerGroup g = null;
                foreach (LayerFilter lf in tree.Root.NestedFilters)
                    if (lf.Name == grp && lf is LayerGroup) { g = (LayerGroup)lf; break; }
                if (g == null) { g = new LayerGroup { Name = grp }; tree.Root.NestedFilters.Add(g); nGrp++; }
                if (!g.LayerIds.Contains(lid)) g.LayerIds.Add(lid);
            }
            db.LayerFilters = tree;
            tr.Commit();
        }
        ed.WriteMessage("\nLAYGROUPS: " + nLay + " layer(s) created, " + nGrp + " group(s) created.");
    }
}

