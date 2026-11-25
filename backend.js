/* HotelesCS: conexión con Supabase (acceso con correo de empresa + datos compartidos).
   Ofrece a la app la misma interfaz que usaba la versión de Claude: db.collection().add/onSnapshot, db.doc().delete, user.id/name/profiles. */
(function () {
  const C = window.RYC_CONFIG || {};
  const T = {
    hotels: {
      toApp: r => ({ id: r.id, name: r.name, city: r.city || "", type: r.type || "Hotel", address: r.address || "", region: r.region || "",
        lat: r.lat, lon: r.lon, osm: r.osm || "", stars: r.stars || "", createdBy: r.created_by, createdAt: Date.parse(r.created_at) }),
      toDb: d => ({ name: d.name, city: d.city || null, type: d.type || null, address: d.address || null, region: d.region || null,
        lat: d.lat ?? null, lon: d.lon ?? null, osm: d.osm || null, stars: d.stars ? String(d.stars) : null })
    },
    reviews: {
      toApp: r => ({ id: r.id, hotelId: r.hotel_id, rating: r.rating, price: r.price, tags: r.tags || [], via: r.via || "", photos: r.photos || [], comment: r.comment || "",
        authorId: r.author_id, createdAt: Date.parse(r.created_at) }),
      toDb: d => ({ hotel_id: d.hotelId, rating: d.rating, price: d.price || null, tags: d.tags || [], via: d.via || null, photos: (d.photos && d.photos.length) ? d.photos : null, comment: d.comment || null })
    }
  };

  const css = `
  #ryc-login{position:fixed;inset:0;z-index:999;background:var(--bg,#f4f3f2);display:flex;align-items:center;justify-content:center;padding:16px;font-family:var(--f-body,system-ui)}
  #ryc-login .box{width:100%;max-width:380px;background:var(--surface,#fff);border-radius:20px;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,.18)}
  #ryc-login .hd{background:linear-gradient(180deg,#1c1c1e,#2c2c30);color:#fff;padding:22px 20px;border-bottom:3px solid var(--brand,#ff5f00)}
  #ryc-login .hd b{font-family:var(--f-head,sans-serif);font-size:30px;letter-spacing:.5px;display:block}
  #ryc-login form{padding:18px 20px;display:grid;gap:12px}
  #ryc-login label{font-size:13px;color:var(--muted,#62605d);display:grid;gap:4px}
  #ryc-login input{font:inherit;font-size:16px;padding:11px 12px;border:1px solid var(--line,#e2dfdc);border-radius:12px;background:var(--surface,#fff);color:var(--fg,#1d1d1f)}
  #ryc-login button{font:inherit;font-weight:600;font-size:16px;padding:12px;border:0;border-radius:12px;background:linear-gradient(135deg,#ff5f00,#ff8a3d);color:#111;cursor:pointer}
  #ryc-login .sw{background:none;color:var(--fg,#1d1d1f);text-decoration:underline;font-weight:500;font-size:14px;padding:4px}
  #ryc-login [hidden]{display:none}
  #ryc-login .err{color:var(--warn,#b4400a);font-size:14px;min-height:1em;margin:0}`;

  function loginScreen(sb) {
    return new Promise(resolve => {
      const st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);
      const el = document.createElement("div"); el.id = "ryc-login";
      el.innerHTML = `<div class="box"><div class="hd"><b>Hoteles<span style="background:linear-gradient(135deg,#ff5f00,#ff8a3d);color:#111;padding:0 7px;border-radius:7px;margin-left:4px">CS</span></b>Reseñas de alojamientos del equipo técnico</div>
        <form novalidate>
          <label>Correo de empresa<input name="email" type="email" autocomplete="email" required placeholder="nombre@${C.domain || "empresa.com"}"></label>
          <label class="nm" hidden>Tu nombre (lo verán los compañeros)<input name="name" autocomplete="name" maxlength="80"></label>
          <label>Contraseña<input name="pw" type="password" autocomplete="current-password" required minlength="6"></label>
          <p class="err" role="alert"></p>
          <button type="submit" class="go">Entrar</button>
          <button type="button" class="sw">¿Primera vez? Crear cuenta</button>
        </form></div>`;
      document.body.appendChild(el);
      const f = el.querySelector("form"), err = el.querySelector(".err"), go = el.querySelector(".go"), sw = el.querySelector(".sw"), nm = el.querySelector(".nm");
      let signup = false;
      sw.onclick = () => { signup = !signup; nm.hidden = !signup; go.textContent = signup ? "Crear cuenta" : "Entrar";
        sw.textContent = signup ? "Ya tengo cuenta" : "¿Primera vez? Crear cuenta"; f.pw.autocomplete = signup ? "new-password" : "current-password"; err.textContent = ""; };
      f.onsubmit = async e => {
        e.preventDefault(); err.textContent = "";
        const email = f.email.value.trim().toLowerCase(), pw = f.pw.value, name = f.name.value.trim();
        if (C.domain && !email.endsWith("@" + C.domain)) return err.textContent = "Usa tu correo de empresa (@" + C.domain + ").";
        if (pw.length < 6) return err.textContent = "La contraseña debe tener al menos 6 caracteres.";
        if (signup && !name) return err.textContent = "Pon tu nombre.";
        go.disabled = true; go.textContent = "Un momento…";
        try {
          const r = signup ? await sb.auth.signUp({ email, password: pw, options: { data: { name } } })
                           : await sb.auth.signInWithPassword({ email, password: pw });
          if (r.error) throw r.error;
          if (!r.data.session) throw new Error("confirm");
          el.remove(); resolve(r.data.session);
        } catch (x) {
          const m = String(x && x.message || "");
          err.textContent = /invalid login/i.test(m) ? "Correo o contraseña incorrectos."
            : /already registered/i.test(m) ? "Ese correo ya tiene cuenta. Pulsa «Ya tengo cuenta»."
            : /correos de empresa|database error/i.test(m) ? "Solo se admiten correos de empresa."
            : m === "confirm" ? "Cuenta creada. Revisa tu correo para confirmarla y luego entra."
            : "No se ha podido entrar. Revisa la conexión.";
        } finally { go.disabled = false; go.textContent = signup ? "Crear cuenta" : "Entrar"; }
      };
    });
  }

  window.rycBackend = async function () {
    const sb = window.supabase.createClient(C.url, C.key, { auth: { persistSession: true, autoRefreshToken: true } });
    let { data: { session } } = await sb.auth.getSession();
    if (!session) session = await loginScreen(sb);
    const me = session.user, meta = me.user_metadata || {};

    const subs = {};
    async function fetchAll(table) {
      const out = []; const step = 1000;
      for (let from = 0; ; from += step) {
        const { data, error } = await sb.from(table).select("*").order("created_at").range(from, from + step - 1);
        if (error) throw error; out.push(...data); if (data.length < step) break;
      }
      return out.map(T[table].toApp);
    }
    async function refresh(table) {
      const s = subs[table]; if (!s) return;
      try { const rows = await fetchAll(table); s.cb({ docs: rows.map(r => ({ id: r.id, data: () => r })) }); }
      catch (e) { s.err && s.err(e); }
    }
    document.addEventListener("visibilitychange", () => { if (!document.hidden) Object.keys(subs).forEach(refresh); });

    const db = {
      collection(table) {
        return {
          async add(d) {
            const row = T[table].toDb(d); if (!row.via) delete row.via; if (!row.photos) delete row.photos;
            let { data, error } = await sb.from(table).insert(row).select("id").single();
            for (const col of ["photos", "via"]) {   // columna aún no creada en Supabase: guardar sin ella
              if (error && col in row && new RegExp(col).test(error.message || "")) { delete row[col]; ({ data, error } = await sb.from(table).insert(row).select("id").single()); }
            }
            if (error && error.code === "23505" && table === "hotels" && d.osm) {   // otro compañero lo añadió a la vez
              ({ data, error } = await sb.from("hotels").select("id").eq("osm", d.osm).single());
            }
            if (error) throw error;
            refresh(table); return { id: data.id };
          },
          onSnapshot(cb, err) {
            subs[table] = { cb, err }; refresh(table);
            sb.channel("ryc-" + table).on("postgres_changes", { event: "*", schema: "public", table }, () => refresh(table)).subscribe();
            return () => { delete subs[table]; };
          }
        };
      },
      doc(path) {
        const [table, id] = path.split("/");
        return { async delete() { const { error } = await sb.from(table).delete().eq("id", id); if (error) throw error; refresh(table); } };
      }
    };

    const user = {
      id: async () => me.id,
      name: async () => meta.name || "",
      async profiles(ids) {
        const { data, error } = await sb.from("profiles").select("id,name").in("id", ids);
        if (error) throw error; const o = {}; for (const p of data) o[p.id] = { name: p.name }; return o;
      }
    };

    const who = document.getElementById("who");
    if (who) { who.title = "Pulsa para cerrar sesión"; who.style.cursor = "pointer";
      who.addEventListener("click", async () => { if (confirm("¿Cerrar sesión?")) { await sb.auth.signOut(); location.reload(); } }); }
    const favs = {
      async list() { const { data, error } = await sb.from("favorites").select("hotel_key"); if (error) throw error; return data.map(r => r.hotel_key); },
      async add(k) { const { error } = await sb.from("favorites").insert({ hotel_key: k }); if (error && error.code !== "23505") throw error; },
      async remove(k) { const { error } = await sb.from("favorites").delete().eq("hotel_key", k); if (error) throw error; }
    };
    return { db, user, favs };
  };
})();
