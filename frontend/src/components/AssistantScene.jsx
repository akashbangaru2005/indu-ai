import React, {useEffect, useRef, useState} from "react";

export default function AssistantScene({status = "idle"}) {
  const host = useRef(null);
  const state = useRef(status);
  const [fallback, setFallback] = useState(false);
  useEffect(() => { state.current = status; }, [status]);

  useEffect(() => {
    let disposed = false;
    let release = () => {};
    import("./three-runtime.js").then((THREE) => {
      if (disposed) return;
      const container = host.current;
      let renderer;
      try { renderer = new THREE.WebGLRenderer({alpha: true, antialias: true, powerPreference: "low-power"}); }
      catch { setFallback(true); return; }
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
      renderer.setClearColor(0x000000, 0);
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      container.appendChild(renderer.domElement);
      container.dataset.renderer = "webgl";
      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(40, 1, .1, 100);
      camera.position.set(0, .15, 7.8);
      const core = new THREE.Group();
      scene.add(core);
      const color = new THREE.Color("#91f6d0");
      const uniforms = {uTime: {value: 0}, uColor: {value: color}, uEnergy: {value: .35}};
      const sphere = new THREE.Mesh(new THREE.IcosahedronGeometry(1.13, 5), new THREE.ShaderMaterial({
        uniforms, transparent: true,
        vertexShader: `varying vec3 vNormal; varying vec3 vPosition; uniform float uTime; uniform float uEnergy;
          void main(){vec3 p=position; p+=normal*sin(p.y*8.0+uTime*1.2)*.019*uEnergy;
          vNormal=normalize(normalMatrix*normal); vPosition=p;
          gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.0);}`,
        fragmentShader: `varying vec3 vNormal; varying vec3 vPosition; uniform float uTime; uniform vec3 uColor;
          void main(){float rim=pow(1.0-abs(dot(normalize(vNormal),vec3(0.,0.,1.))),2.7);
          float bands=pow(.5+.5*sin(vPosition.y*35.+sin(vPosition.x*4.+uTime*.4)*2.),12.);
          float glow=pow(max(0.,dot(normalize(vNormal),normalize(vec3(-.6,.8,1.)))),5.);
          vec3 c=vec3(.025,.09,.095)+uColor*(rim*.85+bands*.10+glow*.42);
          gl_FragColor=vec4(c,.97);}`,
      }));
      core.add(sphere);
      const wire = new THREE.Mesh(new THREE.IcosahedronGeometry(1.2, 2), new THREE.MeshBasicMaterial({color, wireframe: true, transparent: true, opacity: .10}));
      core.add(wire);
      const particles = new Float32Array(1500 * 3);
      for (let i = 0; i < 1500; i++) {
        const y = 1 - (i / 1499) * 2;
        const radius = Math.sqrt(1 - y * y);
        const theta = Math.PI * (3 - Math.sqrt(5)) * i;
        particles.set([Math.cos(theta) * radius * 1.25, y * 1.25, Math.sin(theta) * radius * 1.25], i * 3);
      }
      const dots = new THREE.BufferGeometry();
      dots.setAttribute("position", new THREE.BufferAttribute(particles, 3));
      const points = new THREE.Points(dots, new THREE.PointsMaterial({color, size: .013, transparent: true, opacity: .66, blending: THREE.AdditiveBlending}));
      core.add(points);
      const rings = new THREE.Group();
      scene.add(rings);
      for (let i = 0; i < 3; i++) {
        const ring = new THREE.Mesh(new THREE.TorusGeometry(1.68 + i * .18, i === 0 ? .009 : .004, 8, 160),
          new THREE.MeshBasicMaterial({color, transparent: true, opacity: i === 0 ? .56 : .19}));
        ring.rotation.set(Math.PI / 2.4 + i * .12, i * .6, i * .5);
        rings.add(ring);
      }
      const orbit = new THREE.Mesh(new THREE.SphereGeometry(.035, 12, 12), new THREE.MeshBasicMaterial({color: "#d5fff1"}));
      rings.add(orbit);
      const starPositions = new Float32Array(100 * 3);
      for (let i = 0; i < 100; i++) {
        const angle = i * 2.399;
        const r = 2.3 + (i % 10) / 7;
        starPositions.set([Math.cos(angle) * r, Math.sin(angle) * r * .65, -(i % 8) / 3], i * 3);
      }
      const starGeometry = new THREE.BufferGeometry();
      starGeometry.setAttribute("position", new THREE.BufferAttribute(starPositions, 3));
      scene.add(new THREE.Points(starGeometry, new THREE.PointsMaterial({color: "#86baa7", size: .011, opacity: .45, transparent: true})));
      const pointer = {x: 0, y: 0};
      const move = (event) => {
        const rect = container.getBoundingClientRect();
        pointer.x = ((event.clientX - rect.left) / rect.width - .5) * .6;
        pointer.y = ((event.clientY - rect.top) / rect.height - .5) * .4;
      };
      container.addEventListener("pointermove", move);
      const resetPointer = () => { pointer.x = pointer.y = 0; };
      container.addEventListener("pointerleave", resetPointer);
      const observer = new ResizeObserver(() => {
        const {width, height} = container.getBoundingClientRect();
        if (!width || !height) return;
        renderer.setSize(width, height);
        camera.aspect = width / height;
        camera.position.z = camera.aspect < 1 ? 9.2 : 7.8;
        camera.updateProjectionMatrix();
      });
      observer.observe(container);
      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const timer = new THREE.Timer();
      timer.connect(document);
      const target = new THREE.Color();
      let frame;
      const animate = (timestamp) => {
        frame = requestAnimationFrame(animate);
        timer.update(timestamp);
        if (document.hidden) return;
        const time = reduced ? 0 : timer.getElapsed();
        const active = state.current;
        target.set(active === "thinking" || active === "confirmation" ? "#d5bb83" : active === "speaking" ? "#b5a0f4" : active === "listening" ? "#79dbe7" : "#91f6d0");
        color.lerp(target, .035);
        points.material.color.copy(color);
        wire.material.color.copy(color);
        rings.children.slice(0, 3).forEach(ring => ring.material.color.copy(color));
        uniforms.uTime.value = time;
        uniforms.uEnergy.value = ["idle", "sleeping"].includes(active) ? .35 : 1;
        core.rotation.y = time * .07 + pointer.x;
        core.rotation.x += (pointer.y - core.rotation.x) * .04;
        core.position.y = Math.sin(time * .7) * .045;
        const pulse = active === "speaking" ? 1 + Math.sin(time * 5) * .025 : 1;
        core.scale.setScalar(pulse);
        wire.rotation.y = -time * .04;
        rings.rotation.z = time * .05;
        orbit.position.set(Math.cos(time * .45) * 1.68, Math.sin(time * .45) * .6, Math.sin(time * .45) * 1.55);
        renderer.render(scene, camera);
      };
      animate();
      release = () => {
        cancelAnimationFrame(frame);
        timer.dispose();
        observer.disconnect();
        container.removeEventListener("pointermove", move);
        container.removeEventListener("pointerleave", resetPointer);
        scene.traverse((object) => { object.geometry?.dispose(); if (object.material) object.material.dispose(); });
        renderer.dispose();
        renderer.domElement.remove();
      };
    }).catch(() => { if (!disposed) setFallback(true); });
    return () => { disposed = true; release(); };
  }, []);

  return <div className={`assistant-scene scene-${status}`} ref={host} role="img" aria-label={`Interactive 3D Indu core, ${status}`}>
    {fallback && <div className="scene-fallback"><div/><span>I</span></div>}
  </div>;
}
