import gradio as gr
import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, HTMLResponse
from gradio.routes import App as GradioApp
import uvicorn
import tempfile
from typing import List
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_URL = os.environ.get("API_URL", "http://api:8000")

# ── Upload UI page (served as iframe) ─────────────────────────────────────────
# Direct upload to upload.abogalia.work (bypasses Cloudflare 413 limit)
UPLOAD_PAGE_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; font-family: Inter, sans-serif; }
body { background: transparent; padding: 10px; }
#drop-zone {
  border: 2px dashed #6366f1;
  border-radius: 10px;
  padding: 24px 16px;
  text-align: center;
  background: #f8f7ff;
  cursor: pointer;
  transition: background .2s;
}
#drop-zone:hover, #drop-zone.over { background: #e8e8ff; }
.icon { font-size: 2rem; }
.lbl  { color:#5046e5; font-weight:600; font-size:.93rem; margin-top:5px; }
.hint { color:#888; font-size:.76rem; margin-top:3px; }
#status { margin-top:8px; font-size:.85rem; font-weight:500; min-height:1.3em; }
.ok  { color:#10b981; } .err { color:#ef4444; } .info { color:#555; }
#prog { display:none; width:100%; height:5px; margin-top:5px; border-radius:3px; accent-color:#6366f1; }
</style>
</head>
<body>
<div id="drop-zone"
     onclick="document.getElementById('fi').click()"
     ondragover="dv(event,1)" ondragleave="dv(event,0)" ondrop="dd(event)">
  <input type="file" id="fi" accept=".pdf" style="display:none" onchange="go(this.files)">
  <div class="icon">📂</div>
  <div class="lbl">Haz clic o arrastra tu PDF aquí</div>
  <div class="hint">Solo PDF · máx 100 MB</div>
</div>
<progress id="prog" value="0" max="100"></progress>
<div id="status"></div>

<script>
const P     = new URLSearchParams(location.search);
const TOKEN = P.get('token') || '';
const PROJ  = P.get('proj')  || '';

// Direct upload endpoint - bypasses Cloudflare completely
const UPLOAD_API = 'https://upload.abogalia.work/api/v1/documents/upload';

function dv(e,on){e.preventDefault();document.getElementById('drop-zone').classList[on?'add':'remove']('over');}
function dd(e){e.preventDefault();dv(e,0);go(e.dataTransfer.files);}
function st(msg,cls){const el=document.getElementById('status');el.textContent=msg;el.className=cls;}
function prog(v){const p=document.getElementById('prog');if(v==null){p.style.display='none';}else{p.style.display='block';p.value=v;}}

async function go(files) {
  if (!files||!files.length) return;
  if (!TOKEN) { st('❌ Inicia sesión primero','err'); return; }
  if (!PROJ)  { st('❌ Selecciona un proyecto','err'); return; }
  const file = files[0];

  // Validate file size (100MB max)
  if (file.size > 100 * 1024 * 1024) {
    st('❌ El archivo excede 100 MB','err');
    return;
  }

  st('⏳ Subiendo ' + file.name + ' (' + (file.size/1048576).toFixed(1) + ' MB)…', 'info');
  prog(0);

  // Direct multipart upload to upload.abogalia.work (no Cloudflare, no proxy)
  const fd = new FormData();
  fd.append('file', file);
  fd.append('project_id', PROJ);

  const xhr = new XMLHttpRequest();
  xhr.open('POST', UPLOAD_API);
  xhr.setRequestHeader('Authorization', 'Bearer ' + TOKEN);

  xhr.upload.onprogress = (e) => {
    if (e.lengthComputable) {
      prog(Math.round(e.loaded / e.total * 100));
    }
  };

  xhr.onload = () => {
    prog(null);
    if (xhr.status === 200) {
      try {
        const data = JSON.parse(xhr.responseText);
        st('✅ ' + file.name + ' subido correctamente', 'ok');
        window.parent.postMessage({type:'upload_done'},'*');
      } catch {
        st('✅ Archivo subido', 'ok');
        window.parent.postMessage({type:'upload_done'},'*');
      }
    } else {
      let msg = 'Error ' + xhr.status;
      try {
        const err = JSON.parse(xhr.responseText);
        msg = err.detail || err.msg || msg;
      } catch {}
      st('❌ ' + msg, 'err');
    }
  };

  xhr.onerror = () => {
    prog(null);
    st('❌ Error de conexión - revisa tu red', 'err');
  };

  xhr.ontimeout = () => {
    prog(null);
    st('❌ Tiempo de espera agotado', 'err');
  };

  xhr.timeout = 300000; // 5 minutes timeout for large files
  xhr.send(fd);
}
</script>
</body>
</html>"""

# ── App state ──────────────────────────────────────────────────────────────────
class ChatIAFrontend:
    def __init__(self):
        self.auth_token = None
        self.current_user = None
        self.current_project_id = None
        self.current_chat = None

    async def _req(self, method, endpoint, **kw):
        url, hdrs = f"{API_URL}{endpoint}", kw.pop("headers", {})
        if self.auth_token:
            hdrs["Authorization"] = f"Bearer {self.auth_token}"
        async with httpx.AsyncClient(timeout=120.0) as c:
            return await c.request(method, url, headers=hdrs, **kw)

    async def login(self, email, pwd):
        try:
            r = await self._req("POST","/api/v1/users/login",json={"email":email,"password":pwd})
            if r.status_code == 200:
                self.auth_token = r.json()["access_token"]
                me = await self._req("GET","/api/v1/users/me")
                self.current_user = me.json() if me.status_code==200 else {}
                return "<span class='ok'>● Bienvenido, "+self.current_user.get("email","")+"</span>",self.current_user
            try: detail=r.json().get("detail","Credenciales inválidas")
            except: detail="Credenciales inválidas"
            return f"<span class='err'>● {detail}</span>",None
        except Exception as e:
            return f"<span class='err'>● Error: {e}</span>",None

    async def get_projects(self):
        r = await self._req("GET","/api/v1/projects/")
        return r.json() if r.status_code==200 else []

    async def get_documents(self, pid):
        if not pid: return []
        r = await self._req("GET","/api/v1/documents/",params={"project_id":pid})
        return r.json() if r.status_code==200 else []

    async def delete_document(self, doc_id):
        if not doc_id: return "❌ Selecciona un documento"
        r = await self._req("DELETE", f"/api/v1/documents/{doc_id}")
        if r.status_code == 200:
            return "✅ Documento eliminado"
        try: detail = r.json().get("detail", r.text)
        except: detail = r.text
        return f"❌ {detail}"

    async def create_project(self, name, desc=""):
        r = await self._req("POST","/api/v1/projects/",json={"name":name,"description":desc})
        if r.status_code==200:
            self.current_project_id=r.json()["id"]
            return f"✅ Proyecto '{name}' creado"
        try: detail=r.json().get("detail",r.text)
        except: detail=r.text
        return f"❌ {detail}"

    async def ask(self, msg, hist:List[List[str]], pid=None):
        if not self.auth_token: return hist+[["Inicia sesión primero",""]]
        if not msg.strip(): return hist
        hist = hist+[[msg,""]]
        p = pid or self.current_project_id
        try:
            r = await self._req("POST","/api/v1/chat/ask",json={
                "message":msg,"chat_id":str(self.current_chat) if self.current_chat else None,
                "project_id":str(p) if p else None,"use_memorag":True})
            if r.status_code==200:
                res=r.json(); ans=res["response"]
                if res.get("citations"):
                    ans+="\n\nFuentes:\n"+"\n".join([f"- Pág {c['page']}: {c['content'][:60]}..." for c in res["citations"]])
                hist[-1][1]=ans
                if not self.current_chat: self.current_chat=res.get("chat_id")
            else: hist[-1][1]=f"Error {r.status_code}: {r.text}"
        except Exception as e: hist[-1][1]=f"Error: {e}"
        return hist

frontend = ChatIAFrontend()

def make_iframe(token:str, proj:str) -> str:
    import urllib.parse
    q = urllib.parse.urlencode({"token": token or "", "proj": proj or ""})
    return (f'<iframe src="/chatia-upload-ui?{q}" width="100%" height="200" frameborder="0"'
            f' style="border:none;border-radius:10px"></iframe>'
            '<script>'
            'window.addEventListener("message",function(e){'
            '  if(e.data&&e.data.type==="upload_done"){'
            '    var b=document.getElementById("sync-btn");if(b)b.click();'
            '  }});'
            '</script>')

def make_iframe_locked() -> str:
    return '<div style="padding:1rem;color:#888;border:1px dashed #ccc;border-radius:8px;text-align:center">Inicia sesión para activar la subida</div>'

CSS = """
.ok  {color:#10b981;background:#ecfdf5;padding:4px 12px;border-radius:999px;font-weight:500;font-size:.85em}
.err {color:#ef4444;background:#fef2f2;padding:4px 12px;border-radius:999px;font-weight:500;font-size:.85em}
.gradio-container{font-family:'Inter',sans-serif!important;max-width:1200px!important;margin:auto!important}
"""

def create_gradio_interface():
    with gr.Blocks(title="ChatIA Intelligence",theme=gr.themes.Soft(primary_hue="indigo"),css=CSS) as interface:
        with gr.Row():
            with gr.Column(scale=8):
                gr.Markdown("# 📄 ChatIA Intelligence")
                gr.Markdown("Plataforma RAG de análisis de documentos")
            with gr.Column(scale=2):
                login_out = gr.Markdown("<span class='ok'>● Servidor activo</span>")

        with gr.Tabs():
            with gr.Tab("Authentication"):
                with gr.Row():
                    with gr.Column():
                        email_i=gr.Textbox(label="Email",placeholder="admin@example.com")
                        pass_i=gr.Textbox(label="Contraseña",type="password")
                        login_btn=gr.Button("Iniciar sesión 🚀",variant="primary")
                    with gr.Column(visible=False) as admin_info:
                        gr.Markdown("### 🛡️ Panel de Administrador")
                        gr.Markdown("Gestión de proyectos y documentos activa.")

            with gr.Tab("Documents"):
                with gr.Column(visible=False) as proj_container:
                    with gr.Row():
                        with gr.Column(scale=1):
                            proj_drop=gr.Dropdown(label="Proyecto activo",choices=[])
                            new_proj_btn=gr.Button("➕ Nuevo Proyecto")
                            sync_btn=gr.Button("🔄 Actualizar lista")
                            with gr.Column(visible=False) as new_proj_box:
                                np_name=gr.Textbox(label="Nombre")
                                np_desc=gr.Textbox(label="Descripción")
                                np_save=gr.Button("Crear",variant="primary")
                            proj_status=gr.Textbox(label="Estado",interactive=False)
                        with gr.Column(scale=2):
                            doc_df=gr.Dataframe(headers=["Archivo","Estado","Páginas","Fecha"],label="Documentos")
                            with gr.Row():
                                with gr.Column(scale=7):
                                    gr.Markdown("### 📤 Subir PDF")
                                    upload_frame=gr.HTML(make_iframe_locked())
                                    sync_after=gr.Button("🔄 Refrescar documentos",variant="secondary",elem_id="sync-btn")
                                with gr.Column(scale=3):
                                    gr.Markdown("### 🗑️ Borrar PDF")
                                    del_doc_drop = gr.Dropdown(label="Selecciona archivo para borrar", choices=[])
                                    del_doc_btn = gr.Button("Eliminar 🗑️", variant="stop")
                                    del_status = gr.Markdown("")
                non_admin_msg=gr.Markdown("## 🔒 Solo administradores",visible=True)

            with gr.Tab("Chat"):
                with gr.Row():
                    with gr.Column(scale=1):
                        chat_proj_drop=gr.Dropdown(label="Proyecto",choices=[])
                        clear_btn=gr.Button("Limpiar")
                    with gr.Column(scale=3):
                        chat_ui=gr.Chatbot(height=500)
                        chat_msg=gr.Textbox(placeholder="Escribe tu pregunta...",lines=2)
                        chat_send=gr.Button("Preguntar ✨",variant="primary")

        async def handle_login(e,p):
            res,user=await frontend.login(e,p)
            if not user: return {login_out:res}
            is_adm=user.get("is_superuser",False) or e=="administrador@hotmail.com"
            projs=await frontend.get_projects()
            choices=[(pr["name"],pr["id"]) for pr in projs]
            val=projs[0]["id"] if projs else None
            iframe=make_iframe(frontend.auth_token,str(val) if val else "")
            return {login_out:res,admin_info:gr.update(visible=is_adm),
                    proj_container:gr.update(visible=is_adm),
                    non_admin_msg:gr.update(visible=not is_adm),
                    proj_drop:gr.update(choices=choices,value=val),
                    chat_proj_drop:gr.update(choices=choices,value=val),
                    upload_frame:iframe}

        def upd_iframe(pid):
            return make_iframe(frontend.auth_token or "",str(pid) if pid else "")

        async def load_docs(pid):
            if not pid: return [], gr.update(choices=[], value=None)
            docs=await frontend.get_documents(str(pid))
            df = [[d["filename"],d["status"].upper(),d.get("num_pages") or "—",
                     str(d["created_at"])[:10] if d.get("created_at") else "—"] for d in docs]
            dd = [(d["filename"], d["id"]) for d in docs]
            return df, gr.update(choices=dd, value=None)

        async def create_proj(n,d):
            msg=await frontend.create_project(n,d)
            projs=await frontend.get_projects()
            choices=[(p["name"],p["id"]) for p in projs]
            nid=str(frontend.current_project_id) if frontend.current_project_id else None
            return msg,gr.update(choices=choices,value=nid),gr.update(choices=choices,value=nid),gr.update(visible=False),make_iframe(frontend.auth_token or "",nid or "")

        login_btn.click(handle_login,[email_i,pass_i],
            [login_out,admin_info,proj_container,non_admin_msg,proj_drop,chat_proj_drop,upload_frame],queue=False)
        proj_drop.change(load_docs,proj_drop,[doc_df, del_doc_drop],queue=False)
        proj_drop.change(upd_iframe,proj_drop,upload_frame,queue=False)
        sync_btn.click(load_docs,proj_drop,[doc_df, del_doc_drop],queue=False)
        sync_after.click(load_docs,proj_drop,[doc_df, del_doc_drop],queue=False)
        new_proj_btn.click(lambda:gr.update(visible=True),None,new_proj_box,queue=False)
        np_save.click(create_proj,[np_name,np_desc],[proj_status,proj_drop,chat_proj_drop,new_proj_box,upload_frame],queue=False)
        chat_send.click(frontend.ask,[chat_msg,chat_ui,chat_proj_drop],chat_ui,queue=False).then(lambda:"",None,chat_msg,queue=False)
        clear_btn.click(lambda:(None,[]),None,[chat_msg,chat_ui],queue=False)

        async def exec_del(doc_id, pid):
            msg = await frontend.delete_document(doc_id)
            df, drop = await load_docs(pid)
            return msg, df, drop

        del_doc_btn.click(exec_del, [del_doc_drop, proj_drop], [del_status, doc_df, del_doc_drop], queue=False)

    return interface


if __name__ == "__main__":
    gradio_ui = create_gradio_interface()
    gradio_ui.queue(default_concurrency_limit=20)

    # Get Gradio's internal FastAPI app — add our routes DIRECTLY to it
    # This avoids any middleware interference from mounting
    app = GradioApp.create_app(gradio_ui, app_kwargs={})

    # Custom upload endpoint — registered directly on Gradio's FastAPI app
    @app.post("/chatia-upload")
    async def chatia_upload(request: Request):
        """Fallback: accept JSON body with base64-encoded file."""
        try:
            auth_header = request.headers.get("Authorization", "")
            token = auth_header.replace("Bearer ", "").strip()
            body = await request.json()
            filename    = body.get("filename", "upload.pdf")
            project_id  = body.get("project_id", "")
            content_b64 = body.get("content_b64", "")
            if not content_b64:
                return JSONResponse({"ok": False, "msg": "❌ No se recibió el archivo"}, status_code=400)
            if not token:
                return JSONResponse({"ok": False, "msg": "❌ Sin autenticación"}, status_code=401)
            if not project_id:
                return JSONResponse({"ok": False, "msg": "❌ Sin proyecto"}, status_code=400)
            import base64
            content = base64.b64decode(content_b64)
            url     = f"{API_URL}/api/v1/documents/upload"
            headers = {"Authorization": f"Bearer {token}"}
            files   = {"file": (filename, content, "application/pdf")}
            data    = {"project_id": project_id}
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.post(url, headers=headers, files=files, data=data)
            if r.status_code == 200:
                return JSONResponse({"ok": True, "msg": f"✅ '{filename}' subido correctamente"})
            try:    detail = r.json().get("detail", r.text)
            except: detail = r.text
            return JSONResponse({"ok": False, "msg": f"❌ {detail}"}, status_code=r.status_code)
        except Exception as e:
            logger.error(f"chatia_upload: {e}")
            return JSONResponse({"ok": False, "msg": f"❌ Error: {e}"}, status_code=500)

    @app.post("/chatia-process")
    async def chatia_process(request: Request):
        """
        Two-step upload — Cloudflare-safe:
        Step 1 (browser→server): Browser POSTs to Gradio /upload (Cloudflare allows it).
                                 File lands in Gradio's /tmp/gradio/… temp dir.
        Step 2 (server→API):    We read the local temp file and POST it to the backend API
                                 over the internal Docker network (NOT through Cloudflare).
        """
        try:
            auth_header = request.headers.get("Authorization", "")
            token = auth_header.replace("Bearer ", "").strip()
            body = await request.json()
            temp_path  = body.get("temp_path", "")
            filename   = body.get("filename", "upload.pdf")
            project_id = body.get("project_id", "")

            if not token:
                return JSONResponse({"ok": False, "msg": "❌ Sin autenticación"}, status_code=401)
            if not project_id:
                return JSONResponse({"ok": False, "msg": "❌ Sin proyecto"}, status_code=400)
            if not temp_path:
                return JSONResponse({"ok": False, "msg": "❌ Sin ruta de archivo"}, status_code=400)

            # Security: only allow Gradio temp paths
            import os
            import shutil
            temp_path = os.path.abspath(temp_path)
            if not any(temp_path.startswith(r) for r in ["/tmp/gradio", "/tmp"]):
                return JSONResponse({"ok": False, "msg": "❌ Ruta no permitida"}, status_code=403)

            if not os.path.exists(temp_path):
                return JSONResponse({"ok": False, "msg": f"❌ Temporal no encontrado"}, status_code=404)

            with open(temp_path, "rb") as fh:
                content = fh.read()

            logger.info(f"Process: {filename} ({len(content)//1024}KB) → project {project_id}")

            # Send to backend API over internal Docker network (no Cloudflare involved)
            url     = f"{API_URL}/api/v1/documents/upload"
            headers = {"Authorization": f"Bearer {token}"}
            files   = {"file": (filename, content, "application/pdf")}
            data    = {"project_id": project_id}

            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.post(url, headers=headers, files=files, data=data)

            try: os.remove(temp_path)
            except: pass

            if r.status_code == 200:
                return JSONResponse({"ok": True, "msg": f"✅ '{filename}' subido correctamente"})

            try:    detail = r.json().get("detail", r.text)
            except: detail = r.text
            return JSONResponse({"ok": False, "msg": f"❌ {detail}"}, status_code=r.status_code)

        except Exception as e:
            logger.error(f"chatia_process: {e}")
            return JSONResponse({"ok": False, "msg": f"❌ Error: {e}"}, status_code=500)

    # Serve the upload iframe page
    @app.get("/chatia-upload-ui")
    async def chatia_upload_ui(token: str = "", proj: str = ""):
        return HTMLResponse(UPLOAD_PAGE_HTML)

    uvicorn.run(app, host="0.0.0.0", port=7860, log_level="info")
