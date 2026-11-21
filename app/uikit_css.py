"""CSS κοινής διεπαφής 0.18.0 (σε ξεχωριστό module για να μην υπάρχει κυκλική εισαγωγή με το review)."""
UI_CSS = """
header{position:sticky;top:0;z-index:100}
:root{--c-sel:#1f9d57;--c-opt:#7c4dff;--c-list:#1e6fd9;--c-txt:#d98a00;--c-file:#0f9fa8;--c-danger:#d33;--hh:3rem}
[data-theme=dark]{--c-sel:#3ddc84;--c-opt:#a78bfa;--c-list:#5aa2ff;--c-txt:#ffb84d;--c-file:#35d4dd;--c-danger:#ff6b6b}
input[type=checkbox].r-sel{accent-color:var(--c-sel);width:1.1rem;height:1.1rem;outline:2px solid color-mix(in srgb,var(--c-sel) 55%,transparent);outline-offset:1px;border-radius:3px}
input[type=checkbox].r-opt,input[type=radio].r-opt{accent-color:var(--c-opt);width:1.05rem;height:1.05rem}
label.f.chk,label:has(>input.r-opt){color:var(--fg)}
label:has(>input.r-opt:checked){color:var(--c-opt);font-weight:600}
select.r-list{border:2px solid var(--c-list);background:color-mix(in srgb,var(--c-list) 8%,var(--card))}
input.r-txt,textarea.r-txt{border:2px solid color-mix(in srgb,var(--c-txt) 70%,var(--border));background:color-mix(in srgb,var(--c-txt) 7%,var(--card))}
input.r-txt:focus,textarea.r-txt:focus,select.r-list:focus{outline:2px solid var(--accent)}
input[type=file].r-file{border:2px dashed var(--c-file);border-radius:var(--radius);padding:.25rem;background:color-mix(in srgb,var(--c-file) 8%,var(--card))}
tr.sel-on td{background:color-mix(in srgb,var(--c-sel) 18%,var(--card))!important}
button.danger,.btn.danger{background:var(--c-danger);color:#fff;border-color:var(--c-danger)}
button.danger:hover{filter:brightness(1.1)}
button[disabled]{opacity:.5;cursor:not-allowed}
#tip{position:fixed;z-index:1000;max-width:22rem;background:#1c2330;color:#f2f5fa;border:1px solid #5a6a85;border-radius:6px;padding:.35rem .6rem;font-size:.85rem;line-height:1.3;pointer-events:none;box-shadow:0 4px 14px rgba(0,0,0,.35);display:none}
#tip b{color:#ffd479}
.legend{display:inline-flex;flex-wrap:wrap;gap:.3rem .9rem;font-size:.82rem;margin-left:.6rem}.legend i{display:inline-block;width:.8rem;height:.8rem;border-radius:3px;vertical-align:-1px;margin-right:.25rem}
footer{padding:.6rem 1rem;color:var(--muted);font-size:.85rem}
/* floating εργαλειοθήκη */
#tbfab{position:fixed;right:1rem;bottom:1rem;z-index:90;width:3rem;height:3rem;border-radius:50%;font-size:1.4rem;background:var(--accent);color:#fff;border:0;box-shadow:0 3px 12px rgba(0,0,0,.35);cursor:pointer}
#tbox{position:fixed;right:1rem;bottom:4.6rem;z-index:95;width:17rem;background:var(--card);border:2px solid var(--accent);border-radius:10px;box-shadow:0 6px 24px rgba(0,0,0,.35);display:none;font-size:.9rem}
#tbox .tbh{cursor:move;background:var(--accent);color:#fff;border-radius:7px 7px 0 0;padding:.3rem .6rem;display:flex;justify-content:space-between;align-items:center;user-select:none}
#tbox .tbt{display:flex;gap:2px;padding:.3rem .4rem 0;border-bottom:1px solid var(--border)}#tbox .tbt button{border-radius:6px 6px 0 0;border-bottom:0;padding:.15rem .5rem;font-size:.82rem}#tbox .tbt button.on{background:var(--accent);color:#fff}
#tbox .tbi{display:grid;grid-template-columns:1fr 1fr;gap:.3rem;padding:.5rem;max-height:50vh;overflow:auto}#tbox .tbi a,#tbox .tbi button{display:block;text-align:left;padding:.3rem .45rem;border:1px solid var(--border);border-radius:6px;background:var(--btn);color:var(--btnfg);text-decoration:none;font-size:.85rem;cursor:pointer}
#tbox .tbi a:hover,#tbox .tbi button:hover{border-color:var(--accent)}#tbox .tbf{padding:.2rem .6rem .4rem;font-size:.8rem}
ul.reorder{list-style:none;padding:0;margin:.3rem 0}ul.reorder li{display:flex;align-items:center;gap:.4rem;margin:.12rem 0;padding:.12rem .5rem;border:1px solid var(--border);border-radius:6px;max-width:30rem}ul.reorder li span.t{flex:1}
@media print{header,#tbfab,#tbox,footer,#tip{display:none!important}}
"""
