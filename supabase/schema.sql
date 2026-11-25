-- HotelesCS: tablas, permisos y tiempo real.
-- Pegar entero en Supabase > SQL Editor > New query > Run.
-- Solo correos @kuka.com.

create table if not exists public.profiles (
  id uuid primary key references auth.users on delete cascade,
  name text not null default ''
);

create table if not exists public.hotels (
  id uuid primary key default gen_random_uuid(),
  name text not null check (length(name) between 1 and 200),
  city text, type text, address text, region text,
  lat double precision, lon double precision,
  osm text unique, stars text,
  created_by uuid default auth.uid() references auth.users on delete set null,
  created_at timestamptz not null default now()
);

create table if not exists public.reviews (
  id uuid primary key default gen_random_uuid(),
  hotel_id uuid not null references public.hotels on delete cascade,
  rating int not null check (rating between 1 and 5),
  price int check (price between 0 and 2000),
  tags text[] not null default '{}',
  comment text check (length(comment) <= 500),
  author_id uuid not null default auth.uid() references auth.users on delete cascade,
  created_at timestamptz not null default now()
);

-- Solo correos del dominio de empresa
create or replace function public.is_team() returns boolean
language sql stable as $$
  select coalesce(auth.jwt()->>'email','') ilike '%@kuka.com'
$$;

create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.email is null or new.email not ilike '%@kuka.com' then
    raise exception 'Solo se admiten correos de empresa';
  end if;
  insert into public.profiles(id, name)
  values (new.id, left(coalesce(new.raw_user_meta_data->>'name',''), 80))
  on conflict (id) do nothing;
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

alter table public.profiles enable row level security;
alter table public.hotels   enable row level security;
alter table public.reviews  enable row level security;

drop policy if exists "equipo lee perfiles" on public.profiles;
create policy "equipo lee perfiles" on public.profiles for select to authenticated using (public.is_team());
drop policy if exists "cada uno edita su nombre" on public.profiles;
create policy "cada uno edita su nombre" on public.profiles for update to authenticated using (id = auth.uid()) with check (id = auth.uid());

drop policy if exists "equipo lee hoteles" on public.hotels;
create policy "equipo lee hoteles" on public.hotels for select to authenticated using (public.is_team());
drop policy if exists "equipo añade hoteles" on public.hotels;
create policy "equipo añade hoteles" on public.hotels for insert to authenticated with check (public.is_team() and created_by = auth.uid());

drop policy if exists "equipo lee reseñas" on public.reviews;
create policy "equipo lee reseñas" on public.reviews for select to authenticated using (public.is_team());
drop policy if exists "equipo añade reseñas" on public.reviews;
create policy "equipo añade reseñas" on public.reviews for insert to authenticated with check (public.is_team() and author_id = auth.uid());
drop policy if exists "cada uno borra sus reseñas" on public.reviews;
create policy "cada uno borra sus reseñas" on public.reviews for delete to authenticated using (author_id = auth.uid());

-- Permisos de acceso para usuarios con sesión iniciada (las políticas de arriba limitan qué filas)
grant usage on schema public to authenticated;
grant select, update on public.profiles to authenticated;
grant select, insert on public.hotels to authenticated;
grant select, insert, delete on public.reviews to authenticated;

-- Actualizar la lista en vivo cuando alguien sube una reseña
do $$ begin
  alter publication supabase_realtime add table public.hotels, public.reviews;
exception when duplicate_object then null; end $$;
