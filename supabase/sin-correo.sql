-- HotelesCS: entrar con nombre y apellido + contraseña (sin correo de empresa).
-- Pegar entero en Supabase > SQL Editor > New query > Run. Se puede ejecutar más de una vez.

-- Cualquier persona con sesión iniciada es del equipo (antes: solo correos @kuka.com)
create or replace function public.is_team() returns boolean
language sql stable as $$
  select auth.uid() is not null
$$;

-- Al crear una cuenta se guarda el nombre que verán los compañeros
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles(id, name)
  values (new.id, left(coalesce(new.raw_user_meta_data->>'name',''), 80))
  on conflict (id) do nothing;
  return new;
end $$;
