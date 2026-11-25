# HotelesCS

Reseñas de hoteles y apartamentos para el equipo técnico. Web estática (GitHub Pages) + Supabase gratis (base de datos y acceso con correo de empresa).

## Puesta en marcha (una vez)

1. **Supabase** → crear proyecto (región Europa).
   - *SQL Editor* → pegar `supabase/schema.sql` (con el dominio de empresa en lugar de `__DOMINIO__`) → *Run*.
   - *Authentication → Sign In / Providers → Email*: activado, y **desactivar "Confirm email"** (el correo gratuito de Supabase solo permite unos pocos envíos por hora).
2. `config.js` → poner la *Project URL*, la clave *anon public* y el dominio.
3. **GitHub Pages** → *Settings → Pages → Deploy from a branch → main / (root)*.

## Datos

`hotels-es.json`: catálogo de alojamientos de España, datos © colaboradores de OpenStreetMap (licencia ODbL).
