"use client";

// The Family Twin 3D scene (three.js). Women are spheres and men are cubes (pedigree convention); colour shows
// the engine's exact carrier chance; cousin marriages glow gold. When chances change, the new colours ripple
// outward from the person whose result was recorded, in order of family distance.

// The scene graph is imperative (three.js objects live in a ref and are mutated by the render loop), so the
// compiler's immutability rule does not apply to it.
/* eslint-disable react-hooks/immutability */
import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { layoutPedigree } from "@/lib/pedigreeLayout";
import { distancesFrom, pct, type Result, type TwinClan } from "@/lib/twin";

interface Props {
  clan: TwinClan;
  probs: Record<string, number> | null;
  results: Record<string, Result>;
  selected: string | null;
  onSelect: (id: string | null) => void;
  rippleFrom: string | null;
  origin: string[] | null; // line of descent to highlight
  reducedMotion: boolean;
  label: string;
}

const STOPS: [number, THREE.Color][] = [
  [0, new THREE.Color("#1d3836")],
  [0.03, new THREE.Color("#25625c")],
  [0.12, new THREE.Color("#3fa293")],
  [0.3, new THREE.Color("#b7c25e")],
  [0.5, new THREE.Color("#f0a93a")],
  [0.75, new THREE.Color("#ff8547")],
  [1, new THREE.Color("#fff1d6")],
];
const AFFECTED = new THREE.Color("#ff3d7a");
const GOLD = new THREE.Color("#f2c14e");

function colourFor(p: number, affected: boolean): THREE.Color {
  if (affected) return AFFECTED.clone();
  for (let i = 1; i < STOPS.length; i++) {
    const [p1, c1] = STOPS[i];
    const [p0, c0] = STOPS[i - 1];
    if (p <= p1) return c0.clone().lerp(c1, (p - p0) / (p1 - p0));
  }
  return STOPS[STOPS.length - 1][1].clone();
}

interface Node {
  mesh: THREE.Mesh;
  mat: THREE.MeshStandardMaterial;
  from: THREE.Color;
  to: THREE.Color;
  start: number;
  p: number;
  ring?: THREE.Mesh;
}

export function TwinScene(props: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const tip = useRef<HTMLDivElement>(null);
  const api = useRef<{
    nodes: Map<string, Node>;
    pos: Map<string, THREE.Vector3>;
    group: THREE.Group;
    originGroup: THREE.Group;
    ringGroup: THREE.Group;
    selRing: THREE.Mesh;
    controls: OrbitControls;
    camera: THREE.PerspectiveCamera;
  } | null>(null);
  const latest = useRef(props);
  useEffect(() => {
    latest.current = props;
  });

  // build the scene once per clan
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const { clan } = latest.current;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor("#071719");
    el.appendChild(renderer.domElement);
    renderer.domElement.setAttribute("aria-hidden", "true");

    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog("#071719", 30, 70);
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 200);
    scene.add(new THREE.AmbientLight("#ffffff", 0.55));
    const key = new THREE.DirectionalLight("#fff3dc", 1.1);
    key.position.set(8, 14, 12);
    scene.add(key);
    const rim = new THREE.PointLight("#5fb3ab", 40, 60);
    rim.position.set(-10, -6, -8);
    scene.add(rim);

    // layout: generations as rows; the clan wraps gently around the viewer
    const layout = layoutPedigree({
      people: clan.people.map((p) => ({ id: p.id, sex: p.sex, mother: p.mother, father: p.father })),
      unions: clan.unions.map((u) => ({ a: u.a, b: u.b })),
    });
    const W = Math.max(layout.width, 1);
    const ARC = 1.5;
    const R = (W * 1.05) / ARC;
    const pos = new Map<string, THREE.Vector3>();
    for (const p of clan.people) {
      const a = ((layout.x[p.id] ?? 0) - W / 2) / W * ARC;
      const y = (layout.depth / 2 - (layout.gen[p.id] ?? 0)) * 2.6;
      pos.set(p.id, new THREE.Vector3(R * Math.sin(a), y, -R * (1 - Math.cos(a))));
    }

    const group = new THREE.Group();
    scene.add(group);
    const ringGroup = new THREE.Group();
    group.add(ringGroup);
    const originGroup = new THREE.Group();
    group.add(originGroup);

    // edges
    const lineMat = new THREE.LineBasicMaterial({ color: "#5c8c87", transparent: true, opacity: 0.45 });
    const segs: number[] = [];
    const push = (a: THREE.Vector3, b: THREE.Vector3) => segs.push(a.x, a.y, a.z, b.x, b.y, b.z);
    for (const p of clan.people) {
      if (!p.mother || !p.father) continue;
      const m = pos.get(p.mother)!;
      const f = pos.get(p.father)!;
      const c = pos.get(p.id)!;
      const mid = m.clone().add(f).multiplyScalar(0.5);
      const knee = new THREE.Vector3(mid.x, (mid.y + c.y) / 2, mid.z);
      push(mid, knee);
      push(knee, new THREE.Vector3(c.x, knee.y, c.z));
      push(new THREE.Vector3(c.x, knee.y, c.z), c);
    }
    const consang = new Set(clan.consanguineous.map(([a, b]) => [a, b].sort().join("|")));
    for (const u of clan.unions) {
      const a = pos.get(u.a)!;
      const b = pos.get(u.b)!;
      if (consang.has([u.a, u.b].sort().join("|"))) {
        // cousin marriage: a glowing gold arc
        const mid = a.clone().add(b).multiplyScalar(0.5).add(new THREE.Vector3(0, 0.9, 0));
        const curve = new THREE.QuadraticBezierCurve3(a, mid, b);
        const tube = new THREE.Mesh(
          new THREE.TubeGeometry(curve, 24, 0.07, 8, false),
          new THREE.MeshStandardMaterial({ color: GOLD, emissive: GOLD, emissiveIntensity: 1.2 }),
        );
        tube.userData.pulse = true;
        group.add(tube);
      } else {
        push(a, b);
      }
    }
    const lg = new THREE.BufferGeometry();
    lg.setAttribute("position", new THREE.Float32BufferAttribute(segs, 3));
    group.add(new THREE.LineSegments(lg, lineMat));

    // people
    const sphere = new THREE.SphereGeometry(0.5, 32, 16);
    const cube = new THREE.BoxGeometry(0.84, 0.84, 0.84);
    const nodes = new Map<string, Node>();
    for (const p of clan.people) {
      const affected = p.status === "affected";
      const c = colourFor(0, affected);
      const mat = new THREE.MeshStandardMaterial({
        color: c, emissive: c, emissiveIntensity: 0.25, roughness: 0.35, metalness: 0.1,
        transparent: p.deceased, opacity: p.deceased ? 0.45 : 1,
      });
      const mesh = new THREE.Mesh(p.sex === "female" ? sphere : cube, mat);
      mesh.position.copy(pos.get(p.id)!);
      mesh.userData.id = p.id;
      group.add(mesh);
      nodes.set(p.id, { mesh, mat, from: c.clone(), to: c.clone(), start: 0, p: 0 });
      if (affected) {
        const halo = new THREE.Mesh(
          new THREE.TorusGeometry(0.72, 0.05, 8, 48),
          new THREE.MeshStandardMaterial({ color: AFFECTED, emissive: AFFECTED, emissiveIntensity: 1.5 }),
        );
        halo.position.copy(mesh.position);
        halo.userData.spin = true;
        group.add(halo);
      }
    }
    const selRing = new THREE.Mesh(
      new THREE.TorusGeometry(0.8, 0.045, 8, 48),
      new THREE.MeshBasicMaterial({ color: "#ffffff" }),
    );
    selRing.visible = false;
    group.add(selRing);

    // camera and controls
    const box = new THREE.Box3().setFromObject(group);
    const centre = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    group.position.sub(centre);
    camera.position.set(0, size.y * 0.1, Math.max(size.x * 0.78, size.y * 1.45) + 4);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.minDistance = 6;
    controls.maxDistance = 70;
    controls.autoRotate = !latest.current.reducedMotion;
    controls.autoRotateSpeed = 0.35;
    controls.addEventListener("start", () => (controls.autoRotate = false));

    api.current = { nodes, pos, group, originGroup, ringGroup, selRing, controls, camera };

    // picking
    const ray = new THREE.Raycaster();
    const ndc = new THREE.Vector2();
    const meshes = [...nodes.values()].map((n) => n.mesh);
    const pick = (ev: PointerEvent): string | null => {
      const r = renderer.domElement.getBoundingClientRect();
      ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(ndc, camera);
      const hit = ray.intersectObjects(meshes, false)[0];
      return hit ? (hit.object.userData.id as string) : null;
    };
    let downAt = { x: 0, y: 0 };
    const onDown = (ev: PointerEvent) => (downAt = { x: ev.clientX, y: ev.clientY });
    const onUp = (ev: PointerEvent) => {
      if (Math.hypot(ev.clientX - downAt.x, ev.clientY - downAt.y) > 5) return; // a drag, not a click
      latest.current.onSelect(pick(ev));
    };
    const byId = new Map(clan.people.map((p) => [p.id, p]));
    const onMove = (ev: PointerEvent) => {
      const id = pick(ev);
      const t = tip.current;
      renderer.domElement.style.cursor = id ? "pointer" : "grab";
      if (!t) return;
      if (!id) {
        t.style.opacity = "0";
        return;
      }
      const p = byId.get(id)!;
      const pr = latest.current.probs?.[id];
      t.textContent = `${p.name}${p.deceased ? " (deceased)" : ""} · ${p.status === "affected" ? "affected" : pr === undefined ? "…" : pct(pr)}`;
      const r = el.getBoundingClientRect();
      t.style.transform = `translate(${ev.clientX - r.left + 14}px, ${ev.clientY - r.top + 14}px)`;
      t.style.opacity = "1";
    };
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);
    renderer.domElement.addEventListener("pointermove", onMove);

    const resize = () => {
      const w = el.clientWidth;
      const h = el.clientHeight;
      renderer.setSize(w, h);
      camera.aspect = w / Math.max(h, 1);
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    resize();

    let raf = 0;
    const clock = new THREE.Clock();
    const tick = () => {
      const now = performance.now();
      const t = clock.getElapsedTime();
      for (const n of nodes.values()) {
        const k = Math.min(1, Math.max(0, (now - n.start) / 550));
        const c = n.from.clone().lerp(n.to, k * k * (3 - 2 * k));
        n.mat.color.copy(c);
        n.mat.emissive.copy(c);
        n.mat.emissiveIntensity = 0.2 + 0.9 * n.p;
        const bump = k > 0 && k < 1 ? 1 + 0.35 * Math.sin(Math.PI * k) : 1;
        n.mesh.scale.setScalar(bump);
      }
      group.traverse((o) => {
        if (o.userData.pulse) {
          const m = (o as THREE.Mesh).material as THREE.MeshStandardMaterial;
          m.emissiveIntensity = 0.9 + 0.5 * Math.sin(t * 2.2);
        }
        if (o.userData.spin) o.rotation.y = t * 0.8;
      });
      selRing.rotation.y = t * 1.5;
      controls.update();
      renderer.render(scene, camera);
      raf = requestAnimationFrame(tick);
    };
    tick();

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      controls.dispose();
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.domElement.removeEventListener("pointerup", onUp);
      renderer.domElement.removeEventListener("pointermove", onMove);
      scene.traverse((o) => {
        const m = o as THREE.Mesh;
        if (m.geometry) m.geometry.dispose();
        const mat = m.material as THREE.Material | THREE.Material[] | undefined;
        if (Array.isArray(mat)) mat.forEach((x) => x.dispose());
        else mat?.dispose();
      });
      renderer.dispose();
      el.removeChild(renderer.domElement);
      api.current = null;
    };
  }, [props.clan]);

  // new chances: ripple outward from the person whose result changed
  useEffect(() => {
    const a = api.current;
    const { probs, rippleFrom, clan, reducedMotion } = props;
    if (!a || !probs) return;
    const dist = rippleFrom ? distancesFrom(clan, rippleFrom) : {};
    const now = performance.now();
    const affected = new Set(clan.people.filter((p) => p.status === "affected").map((p) => p.id));
    for (const [id, n] of a.nodes) {
      const p = probs[id] ?? 0;
      n.from = n.mat.color.clone();
      n.to = colourFor(p, affected.has(id));
      n.p = affected.has(id) ? 1 : p;
      n.start = now + (reducedMotion ? 0 : (dist[id] ?? 0) * 140);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.probs, props.rippleFrom]);

  // rings on tested people, and the selection ring
  useEffect(() => {
    const a = api.current;
    if (!a) return;
    a.ringGroup.clear();
    const all: Record<string, string> = {};
    for (const p of props.clan.people) if (p.test) all[p.id] = p.test.detected.length ? "carrier" : "clear";
    Object.assign(all, props.results);
    for (const [id, r] of Object.entries(all)) {
      const at = a.pos.get(id);
      if (!at) continue;
      const col = r === "clear" ? new THREE.Color("#bfe9e3") : GOLD;
      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(0.62, 0.04, 8, 40),
        new THREE.MeshBasicMaterial({ color: col }),
      );
      ring.position.copy(at);
      ring.rotation.x = Math.PI / 2;
      a.ringGroup.add(ring);
    }
    if (props.selected && a.pos.get(props.selected)) {
      a.selRing.visible = true;
      a.selRing.position.copy(a.pos.get(props.selected)!);
    } else {
      a.selRing.visible = false;
    }
  }, [props.results, props.selected, props.clan]);

  // the line of descent to the most likely source
  useEffect(() => {
    const a = api.current;
    if (!a) return;
    a.originGroup.clear();
    const path = props.origin;
    if (!path || path.length < 2) return;
    const pts = path.map((id) => a.pos.get(id)!).filter(Boolean);
    const curve = new THREE.CatmullRomCurve3(pts);
    const tube = new THREE.Mesh(
      new THREE.TubeGeometry(curve, 80, 0.09, 8, false),
      new THREE.MeshStandardMaterial({ color: "#ffd27a", emissive: "#ffb347", emissiveIntensity: 1.6, transparent: true, opacity: 0.9 }),
    );
    tube.userData.pulse = true;
    a.originGroup.add(tube);
    const top = pts[pts.length - 1];
    const halo = new THREE.Mesh(
      new THREE.SphereGeometry(1.1, 32, 16),
      new THREE.MeshBasicMaterial({ color: "#ffd27a", transparent: true, opacity: 0.18 }),
    );
    halo.position.copy(top);
    a.originGroup.add(halo);
  }, [props.origin]);

  return (
    <div className="relative h-full w-full overflow-hidden rounded-2xl" role="img" aria-label={props.label}>
      <div ref={wrap} className="absolute inset-0" />
      <div
        ref={tip}
        className="pointer-events-none absolute left-0 top-0 rounded-md bg-black/75 px-2 py-1 text-xs text-white opacity-0 transition-opacity"
        style={{ willChange: "transform" }}
      />
    </div>
  );
}
