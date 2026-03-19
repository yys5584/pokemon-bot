# Battle VFX Research — Three.js / WebGL / GLSL Reference

> Comprehensive reference for AAA-quality Pokemon battle visualization.
> Target: Three.js r170+, WebGL 2.0, mobile-compatible where possible.

---

## Table of Contents

1. [GLSL Noise Foundations](#1-glsl-noise-foundations)
2. [Shader-Based Fire Effects](#2-shader-based-fire-effects)
3. [Shader-Based Lightning / Electric Effects](#3-shader-based-lightning--electric-effects)
4. [Shader-Based Psychic / Energy Effects](#4-shader-based-psychic--energy-effects)
5. [Post-Processing Impact Effects](#5-post-processing-impact-effects)
6. [Sound Effects for Battle](#6-sound-effects-for-battle)
7. [Howler.js Integration](#7-howlerjs-integration)
8. [Pokeball Animation](#8-pokeball-animation)
9. [Crowd / Spectator System](#9-crowd--spectator-system)
10. [Trainer Models](#10-trainer-models)
11. [Three.js ShaderMaterial Patterns](#11-threejs-shadermaterial-patterns)
12. [God Rays / Volumetric Light](#12-god-rays--volumetric-light)
13. [Performance Optimization](#13-performance-optimization)

---

## 1. GLSL Noise Foundations

All VFX shaders rely on noise functions. These are the building blocks.

### 1.1 Hash / Random Functions

```glsl
float rand(vec2 c) {
    return fract(sin(dot(c.xy, vec2(12.9898, 78.233))) * 43758.5453);
}

float hash(float n) {
    return fract(sin(n) * 1e4);
}

float hash(vec2 p) {
    return fract(1e4 * sin(17.0 * p.x + p.y * 0.1) *
                 (0.1 + abs(sin(p.y * 13.0 + p.x))));
}
```

### 1.2 Simplex Noise 2D

```glsl
vec3 permute(vec3 x) { return mod(((x * 34.0) + 1.0) * x, 289.0); }

float snoise(vec2 v) {
    const vec4 C = vec4(0.211324865405187, 0.366025403784439,
                        -0.577350269189626, 0.024390243902439);
    vec2 i  = floor(v + dot(v, C.yy));
    vec2 x0 = v - i + dot(i, C.xx);
    vec2 i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
    vec4 x12 = x0.xyxy + C.xxzz;
    x12.xy -= i1;
    i = mod(i, 289.0);
    vec3 p = permute(permute(i.y + vec3(0.0, i1.y, 1.0))
                     + i.x + vec3(0.0, i1.x, 1.0));
    vec3 m = max(0.5 - vec3(dot(x0, x0), dot(x12.xy, x12.xy),
                             dot(x12.zw, x12.zw)), 0.0);
    m = m * m;
    m = m * m;
    vec3 x = 2.0 * fract(p * C.www) - 1.0;
    vec3 h = abs(x) - 0.5;
    vec3 ox = floor(x + 0.5);
    vec3 a0 = x - ox;
    m *= 1.79284291400159 - 0.85373472095314 * (a0 * a0 + h * h);
    vec3 g;
    g.x  = a0.x  * x0.x  + h.x  * x0.y;
    g.yz = a0.yz * x12.xz + h.yz * x12.yw;
    return 130.0 * dot(m, g);
}
```

### 1.3 Simplex Noise 3D

```glsl
vec4 permute(vec4 x) { return mod(((x * 34.0) + 1.0) * x, 289.0); }
vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

float snoise(vec3 v) {
    const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
    const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);

    vec3 i  = floor(v + dot(v, C.yyy));
    vec3 x0 = v - i + dot(i, C.xxx);

    vec3 g = step(x0.yzx, x0.xyz);
    vec3 l = 1.0 - g;
    vec3 i1 = min(g.xyz, l.zxy);
    vec3 i2 = max(g.xyz, l.zxy);

    vec3 x1 = x0 - i1 + C.xxx;
    vec3 x2 = x0 - i2 + 2.0 * C.xxx;
    vec3 x3 = x0 - 1.0 + 3.0 * C.xxx;

    i = mod(i, 289.0);
    vec4 p = permute(permute(permute(
                 i.z + vec4(0.0, i1.z, i2.z, 1.0))
               + i.y + vec4(0.0, i1.y, i2.y, 1.0))
               + i.x + vec4(0.0, i1.x, i2.x, 1.0));

    float n_ = 1.0 / 7.0;
    vec3 ns = n_ * D.wyz - D.xzx;
    vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
    vec4 x_ = floor(j * ns.z);
    vec4 y_ = floor(j - 7.0 * x_);
    vec4 x = x_ * ns.x + ns.yyyy;
    vec4 y = y_ * ns.x + ns.yyyy;
    vec4 h = 1.0 - abs(x) - abs(y);

    vec4 b0 = vec4(x.xy, y.xy);
    vec4 b1 = vec4(x.zw, y.zw);
    vec4 s0 = floor(b0) * 2.0 + 1.0;
    vec4 s1 = floor(b1) * 2.0 + 1.0;
    vec4 sh = -step(h, vec4(0.0));
    vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
    vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;

    vec3 p0 = vec3(a0.xy, h.x);
    vec3 p1 = vec3(a0.zw, h.y);
    vec3 p2 = vec3(a1.xy, h.z);
    vec3 p3 = vec3(a1.zw, h.w);

    vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2,p2), dot(p3,p3)));
    p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;

    vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
    m = m * m;
    return 42.0 * dot(m * m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
}
```

### 1.4 Classic Perlin Noise 2D

```glsl
vec2 fade(vec2 t) { return t * t * t * (t * (t * 6.0 - 15.0) + 10.0); }

float cnoise(vec2 P) {
    vec4 Pi = floor(P.xyxy) + vec4(0.0, 0.0, 1.0, 1.0);
    vec4 Pf = fract(P.xyxy) - vec4(0.0, 0.0, 1.0, 1.0);
    Pi = mod(Pi, 289.0);
    vec4 ix = Pi.xzxz;
    vec4 iy = Pi.yyww;
    vec4 fx = Pf.xzxz;
    vec4 fy = Pf.yyww;
    vec4 i = permute(permute(ix) + iy);
    vec4 gx = 2.0 * fract(i * 0.0243902439) - 1.0;
    vec4 gy = abs(gx) - 0.5;
    vec4 tx = floor(gx + 0.5);
    gx = gx - tx;
    vec2 g00 = vec2(gx.x, gy.x);
    vec2 g10 = vec2(gx.y, gy.y);
    vec2 g01 = vec2(gx.z, gy.z);
    vec2 g11 = vec2(gx.w, gy.w);
    vec4 norm = 1.79284291400159 - 0.85373472095314 *
        vec4(dot(g00,g00), dot(g01,g01), dot(g10,g10), dot(g11,g11));
    g00 *= norm.x; g01 *= norm.y; g10 *= norm.z; g11 *= norm.w;
    float n00 = dot(g00, vec2(fx.x, fy.x));
    float n10 = dot(g10, vec2(fx.y, fy.y));
    float n01 = dot(g01, vec2(fx.z, fy.z));
    float n11 = dot(g11, vec2(fx.w, fy.w));
    vec2 fade_xy = fade(Pf.xy);
    vec2 n_x = mix(vec2(n00, n01), vec2(n10, n11), fade_xy.x);
    float n_xy = mix(n_x.x, n_x.y, fade_xy.y);
    return 2.3 * n_xy;
}
```

### 1.5 Fractional Brownian Motion (FBM)

Used to layer noise for natural-looking turbulence (fire, clouds, energy fields).

```glsl
#define NUM_OCTAVES 5

float fbm(vec2 x) {
    float v = 0.0;
    float a = 0.5;
    vec2 shift = vec2(100.0);
    mat2 rot = mat2(cos(0.5), sin(0.5), -sin(0.5), cos(0.5));
    for (int i = 0; i < NUM_OCTAVES; ++i) {
        v += a * snoise(x);
        x = rot * x * 2.0 + shift;
        a *= 0.5;
    }
    return v;
}

float fbm(vec3 x) {
    float v = 0.0;
    float a = 0.5;
    vec3 shift = vec3(100.0);
    for (int i = 0; i < NUM_OCTAVES; ++i) {
        v += a * snoise(x);
        x = x * 2.0 + shift;
        a *= 0.5;
    }
    return v;
}
```

> Source: https://gist.github.com/patriciogonzalezvivo/670c22f3966e662d2f83
> Also see: https://lygia.xyz/generative for production-quality implementations.

---

## 2. Shader-Based Fire Effects

### 2.1 Concept

Fire is created by layering FBM noise, distorting UV coordinates over time, and mapping the result through a fire color gradient. The key insight: fire rises (UV.y drives intensity), turbulence increases with height, and colors go black -> red -> orange -> yellow -> white at the hottest point.

### 2.2 Fire Vortex Fragment Shader (Cross Flame Style)

This creates a swirling fire vortex suitable for a "Cross Flame" or "Flamethrower" attack.

```glsl
// fire_vortex.frag — Full-screen fire vortex
precision highp float;

uniform float uTime;
uniform vec2 uResolution;
uniform vec2 uOrigin;       // attack source position (normalized 0-1)
uniform vec2 uTarget;       // attack target position (normalized 0-1)
uniform float uIntensity;   // 0.0 = off, 1.0 = full blast
uniform float uVortexSpeed; // rotation speed

// --- Noise (include snoise from Section 1) ---
// [paste snoise2D here]

float fbm_fire(vec2 p) {
    float f = 0.0;
    float a = 0.5;
    mat2 rot = mat2(cos(0.5), sin(0.5), -sin(0.5), cos(0.5));
    for (int i = 0; i < 6; i++) {
        f += a * snoise(p);
        p = rot * p * 2.02;
        a *= 0.5;
    }
    return f;
}

vec3 fireColor(float t) {
    // Physically-inspired fire gradient
    vec3 c1 = vec3(0.0, 0.0, 0.0);       // black (cool)
    vec3 c2 = vec3(0.5, 0.0, 0.0);       // dark red
    vec3 c3 = vec3(1.0, 0.3, 0.0);       // orange
    vec3 c4 = vec3(1.0, 0.7, 0.0);       // yellow-orange
    vec3 c5 = vec3(1.0, 1.0, 0.6);       // white-yellow (hot core)

    t = clamp(t, 0.0, 1.0);
    if (t < 0.25) return mix(c1, c2, t / 0.25);
    if (t < 0.5)  return mix(c2, c3, (t - 0.25) / 0.25);
    if (t < 0.75) return mix(c3, c4, (t - 0.5) / 0.25);
    return mix(c4, c5, (t - 0.75) / 0.25);
}

void main() {
    vec2 uv = gl_FragCoord.xy / uResolution;
    vec2 center = mix(uOrigin, uTarget, 0.5);

    // Convert to polar coordinates for vortex
    vec2 delta = uv - center;
    float dist = length(delta);
    float angle = atan(delta.y, delta.x);

    // Vortex distortion — rotate based on distance and time
    float vortex = angle + dist * 4.0 * sin(uTime * uVortexSpeed) +
                   uTime * uVortexSpeed;

    // Fire UV: use vortex angle + distance for FBM input
    vec2 fireUV = vec2(
        vortex * 0.5 + uTime * 0.3,
        dist * 3.0 - uTime * 1.5  // fire "rises" outward
    );

    float n = fbm_fire(fireUV * 3.0);

    // Shape: beam from origin to target
    vec2 beamDir = normalize(uTarget - uOrigin);
    float beamLen = length(uTarget - uOrigin);
    vec2 toPixel = uv - uOrigin;
    float proj = dot(toPixel, beamDir);
    float perp = length(toPixel - proj * beamDir);

    // Beam envelope
    float beamWidth = 0.08 + 0.04 * sin(uTime * 5.0);
    float beam = smoothstep(beamWidth, 0.0, perp) *
                 smoothstep(-0.05, 0.1, proj) *
                 smoothstep(beamLen + 0.1, beamLen * 0.5, proj);

    // Combine noise with beam shape
    float fire = beam * (n * 0.5 + 0.5) * uIntensity;
    fire = pow(fire, 0.8); // gamma for brighter look

    vec3 color = fireColor(fire);

    // Additive glow at core
    color += vec3(1.0, 0.5, 0.1) * pow(beam * uIntensity, 3.0) * 0.5;

    // Alpha for compositing
    float alpha = smoothstep(0.01, 0.1, fire);

    gl_FragColor = vec4(color, alpha);
}
```

### 2.3 Fire Plane Shader (Campfire / Ember Style)

For a fire that burns upward from a surface (like a Fire Punch or Ember).

```glsl
// fire_plane.frag
precision highp float;

uniform float uTime;
uniform vec2 uResolution;
uniform float uIntensity;

// [include snoise2D and fbm from Section 1]

void main() {
    vec2 uv = gl_FragCoord.xy / uResolution;
    uv.x *= uResolution.x / uResolution.y; // aspect correction

    // Fire distortion
    vec2 q = vec2(0.0);
    q.x = fbm(uv + vec2(0.0, 0.0) + 0.16 * uTime);
    q.y = fbm(uv + vec2(5.2, 1.3) + 0.12 * uTime);

    vec2 r = vec2(0.0);
    r.x = fbm(uv + 4.0 * q + vec2(1.7, 9.2) + 0.15 * uTime);
    r.y = fbm(uv + 4.0 * q + vec2(8.3, 2.8) + 0.126 * uTime);

    float f = fbm(uv + 4.0 * r);

    // Vertical fade (fire rises)
    float verticalFade = 1.0 - uv.y;
    verticalFade = pow(verticalFade, 1.5);

    f = f * verticalFade * uIntensity;

    // Color mapping
    vec3 color = mix(vec3(0.1, 0.0, 0.0),
                     vec3(0.9, 0.2, 0.0),
                     clamp(f * f * 4.0, 0.0, 1.0));
    color = mix(color,
                vec3(1.0, 0.6, 0.0),
                clamp(f * f * f * 8.0, 0.0, 1.0));
    color = mix(color,
                vec3(1.0, 1.0, 0.8),
                clamp(pow(f, 5.0) * 2.0, 0.0, 1.0));

    gl_FragColor = vec4(color, clamp(f * 3.0, 0.0, 1.0));
}
```

### 2.4 Three.js Integration — Fire Attack

```javascript
import * as THREE from 'three';

// Fire attack plane that flies from attacker to defender
function createFireAttack(scene) {
    const fireUniforms = {
        uTime:       { value: 0 },
        uResolution: { value: new THREE.Vector2(512, 512) },
        uOrigin:     { value: new THREE.Vector2(0.1, 0.5) },
        uTarget:     { value: new THREE.Vector2(0.9, 0.5) },
        uIntensity:  { value: 0.0 },
        uVortexSpeed:{ value: 2.0 }
    };

    const fireMaterial = new THREE.ShaderMaterial({
        uniforms: fireUniforms,
        vertexShader: `
            varying vec2 vUv;
            void main() {
                vUv = uv;
                gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            }
        `,
        fragmentShader: fireVortexFrag, // from Section 2.2
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        side: THREE.DoubleSide
    });

    // Full-screen quad for the fire overlay
    const fireQuad = new THREE.Mesh(
        new THREE.PlaneGeometry(2, 2),
        fireMaterial
    );
    fireQuad.frustumCulled = false;
    scene.add(fireQuad);

    return {
        mesh: fireQuad,
        uniforms: fireUniforms,
        update(dt) {
            fireUniforms.uTime.value += dt;
        },
        setIntensity(v) {
            fireUniforms.uIntensity.value = v;
        }
    };
}
```

### 2.5 Fire Particle System (Supplementary Sparks)

```javascript
function createFireParticles(scene, count = 200) {
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(count * 3);
    const velocities = new Float32Array(count * 3);
    const lifetimes = new Float32Array(count);
    const sizes = new Float32Array(count);

    for (let i = 0; i < count; i++) {
        positions[i * 3]     = (Math.random() - 0.5) * 0.5;
        positions[i * 3 + 1] = Math.random() * 0.2;
        positions[i * 3 + 2] = (Math.random() - 0.5) * 0.5;
        velocities[i * 3]     = (Math.random() - 0.5) * 2.0;
        velocities[i * 3 + 1] = 2.0 + Math.random() * 3.0;
        velocities[i * 3 + 2] = (Math.random() - 0.5) * 2.0;
        lifetimes[i] = Math.random();
        sizes[i] = 2.0 + Math.random() * 6.0;
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('aVelocity', new THREE.BufferAttribute(velocities, 3));
    geometry.setAttribute('aLifetime', new THREE.BufferAttribute(lifetimes, 1));
    geometry.setAttribute('aSize', new THREE.BufferAttribute(sizes, 1));

    const material = new THREE.ShaderMaterial({
        uniforms: {
            uTime: { value: 0 },
            uColor1: { value: new THREE.Color(1.0, 0.3, 0.0) },
            uColor2: { value: new THREE.Color(1.0, 0.8, 0.0) }
        },
        vertexShader: `
            attribute vec3 aVelocity;
            attribute float aLifetime;
            attribute float aSize;
            uniform float uTime;
            varying float vLife;

            void main() {
                float t = fract(aLifetime + uTime * 0.5);
                vLife = 1.0 - t;
                vec3 pos = position + aVelocity * t;
                pos.y += t * t * 2.0; // accelerate upward
                vec4 mvPos = modelViewMatrix * vec4(pos, 1.0);
                gl_PointSize = aSize * vLife * (300.0 / -mvPos.z);
                gl_Position = projectionMatrix * mvPos;
            }
        `,
        fragmentShader: `
            uniform vec3 uColor1;
            uniform vec3 uColor2;
            varying float vLife;

            void main() {
                float d = length(gl_PointCoord - 0.5) * 2.0;
                if (d > 1.0) discard;
                float alpha = (1.0 - d) * vLife;
                vec3 color = mix(uColor1, uColor2, vLife);
                gl_FragColor = vec4(color, alpha);
            }
        `,
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false
    });

    const points = new THREE.Points(geometry, material);
    scene.add(points);
    return { mesh: points, uniforms: material.uniforms };
}
```

### 2.6 Shadertoy References for Fire

- **"Flame" by iq** — `shadertoy.com/view/MdX3zr` — Classic raymarched flame
- **"Fire Shader" by duke** — `shadertoy.com/view/4tlSzl` — FBM-based fire
- **"Volcanic" by nimitz** — `shadertoy.com/view/XslGRr` — Detailed volumetric fire
- **"Inigo Quilez fire article"** — `iquilezles.org/articles/fbm/` — FBM theory

---

## 3. Shader-Based Lightning / Electric Effects

### 3.1 Concept

Lightning is created by generating random branching paths. Key techniques:
- **Midpoint displacement** for jagged bolt paths
- **FBM noise** along a line for organic displacement
- **Glow falloff** from the bolt center using exponential decay
- **Branching** via recursive subdivision

### 3.2 Lightning Bolt Fragment Shader

```glsl
// lightning.frag — Electric bolt between two points
precision highp float;

uniform float uTime;
uniform vec2 uResolution;
uniform vec2 uStart;     // bolt start (normalized)
uniform vec2 uEnd;       // bolt end (normalized)
uniform float uIntensity;
uniform vec3 uColor;     // e.g., vec3(0.4, 0.6, 1.0) for blue-white

// [include rand, snoise from Section 1]

float lightning(vec2 uv, vec2 a, vec2 b, float thickness) {
    vec2 ab = b - a;
    float len = length(ab);
    vec2 dir = ab / len;
    vec2 normal = vec2(-dir.y, dir.x);

    vec2 ap = uv - a;
    float t = clamp(dot(ap, dir) / len, 0.0, 1.0);
    float d = abs(dot(ap, normal));

    // Jagged displacement using layered noise
    float displacement = 0.0;
    float freq = 10.0;
    float amp = 0.03;
    for (int i = 0; i < 5; i++) {
        displacement += snoise(vec2(t * freq + uTime * 8.0, float(i) * 1.7)) * amp;
        freq *= 2.0;
        amp *= 0.5;
    }

    d = abs(d - displacement);

    // Core + glow
    float core = exp(-d * d / (thickness * thickness * 0.001));
    float glow = exp(-d * d / (thickness * thickness * 0.02));

    return core * 0.8 + glow * 0.4;
}

void main() {
    vec2 uv = gl_FragCoord.xy / uResolution;
    float aspect = uResolution.x / uResolution.y;
    uv.x *= aspect;

    vec2 start = uStart * vec2(aspect, 1.0);
    vec2 end = uEnd * vec2(aspect, 1.0);

    float bolt = 0.0;

    // Main bolt
    bolt += lightning(uv, start, end, 1.0);

    // Branch bolts
    for (int i = 0; i < 3; i++) {
        float t = 0.2 + float(i) * 0.25;
        vec2 branchStart = mix(start, end, t);
        float angle = snoise(vec2(float(i), uTime)) * 1.0;
        vec2 branchEnd = branchStart + vec2(cos(angle), sin(angle)) * 0.15;
        bolt += lightning(uv, branchStart, branchEnd, 0.5) * 0.6;
    }

    // Flickering
    float flicker = 0.7 + 0.3 * sin(uTime * 30.0 + snoise(vec2(uTime * 10.0, 0.0)) * 6.28);

    bolt *= flicker * uIntensity;

    vec3 color = uColor * bolt;

    // White-hot core
    color += vec3(1.0) * pow(bolt, 4.0) * 0.5;

    gl_FragColor = vec4(color, clamp(bolt, 0.0, 1.0));
}
```

### 3.3 Electric Arc / Tesla Coil Shader

```glsl
// electric_arc.frag — Crackling arc around a pokemon
precision highp float;

uniform float uTime;
uniform vec2 uResolution;
uniform vec2 uCenter;
uniform float uRadius;
uniform float uIntensity;

// [include noise functions]

float electricArc(vec2 uv, float angle, float radius) {
    vec2 dir = vec2(cos(angle), sin(angle));
    vec2 pos = uCenter + dir * radius;

    // Arc distortion
    float noise = snoise(vec2(angle * 5.0, uTime * 15.0));
    pos += vec2(-dir.y, dir.x) * noise * 0.05;

    float d = length(uv - pos);
    return exp(-d * d * 2000.0);
}

void main() {
    vec2 uv = gl_FragCoord.xy / uResolution;
    float aspect = uResolution.x / uResolution.y;
    uv.x *= aspect;
    vec2 center = uCenter * vec2(aspect, 1.0);

    float electric = 0.0;

    // Multiple arcs around the pokemon
    for (int i = 0; i < 8; i++) {
        float baseAngle = float(i) * 6.2831 / 8.0;
        float angle = baseAngle + sin(uTime * 3.0 + float(i)) * 0.5;

        // Random radius jitter
        float r = uRadius * (0.8 + 0.4 * snoise(vec2(float(i), uTime * 5.0)));

        // Segmented arc path
        int segments = 6;
        for (int s = 0; s < 6; s++) {
            float t0 = float(s) / float(segments);
            float t1 = float(s + 1) / float(segments);

            vec2 p0 = center + vec2(cos(angle), sin(angle)) * r * t0;
            vec2 p1 = center + vec2(cos(angle), sin(angle)) * r * t1;

            // Displace midpoint
            vec2 mid = (p0 + p1) * 0.5;
            vec2 perp = normalize(vec2(-(p1-p0).y, (p1-p0).x));
            mid += perp * snoise(vec2(float(s) * 3.0, uTime * 20.0)) * 0.02;

            // Distance to line segment
            vec2 ab = mid - p0;
            vec2 ap = uv - p0;
            float proj = clamp(dot(ap, ab) / dot(ab, ab), 0.0, 1.0);
            float dist = length(ap - ab * proj);

            electric += exp(-dist * dist * 5000.0) * 0.3;
        }
    }

    // Flickering intensity
    float flicker = 0.5 + 0.5 * fract(sin(uTime * 47.0) * 43758.5);
    electric *= flicker * uIntensity;

    vec3 color = vec3(0.3, 0.5, 1.0) * electric;
    color += vec3(0.8, 0.9, 1.0) * pow(electric, 3.0); // white-hot core

    gl_FragColor = vec4(color, clamp(electric, 0.0, 1.0));
}
```

### 3.4 Three.js Integration — Lightning Bolt Mesh

For a 3D lightning bolt using midpoint displacement:

```javascript
function createLightningBolt(start, end, generations = 5) {
    let points = [start.clone(), end.clone()];

    // Midpoint displacement algorithm
    for (let gen = 0; gen < generations; gen++) {
        const newPoints = [points[0]];
        const offset = 0.5 / Math.pow(2, gen); // displacement decreases per generation

        for (let i = 0; i < points.length - 1; i++) {
            const mid = new THREE.Vector3().addVectors(points[i], points[i + 1]).multiplyScalar(0.5);

            // Random perpendicular displacement
            const dir = new THREE.Vector3().subVectors(points[i + 1], points[i]);
            const perp = new THREE.Vector3(
                Math.random() - 0.5,
                Math.random() - 0.5,
                Math.random() - 0.5
            ).cross(dir).normalize();

            mid.addScaledVector(perp, (Math.random() - 0.5) * offset * dir.length());
            newPoints.push(mid, points[i + 1]);
        }
        points = newPoints;
    }

    // Create tube geometry along the bolt path
    const curve = new THREE.CatmullRomCurve3(points);
    const tubeGeometry = new THREE.TubeGeometry(curve, points.length * 2, 0.02, 6, false);

    const material = new THREE.ShaderMaterial({
        uniforms: {
            uTime: { value: 0 },
            uColor: { value: new THREE.Color(0.4, 0.7, 1.0) },
            uGlowColor: { value: new THREE.Color(0.8, 0.9, 1.0) }
        },
        vertexShader: `
            varying vec2 vUv;
            varying vec3 vNormal;
            void main() {
                vUv = uv;
                vNormal = normalMatrix * normal;
                gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            }
        `,
        fragmentShader: `
            uniform float uTime;
            uniform vec3 uColor;
            uniform vec3 uGlowColor;
            varying vec2 vUv;
            varying vec3 vNormal;

            void main() {
                // Core brightness based on tube center
                float core = 1.0 - abs(vUv.y - 0.5) * 2.0;
                core = pow(core, 2.0);

                // Flickering
                float flicker = 0.7 + 0.3 * sin(uTime * 50.0 + vUv.x * 20.0);

                vec3 color = mix(uColor, uGlowColor, core) * flicker;
                float alpha = core * flicker;

                gl_FragColor = vec4(color, alpha);
            }
        `,
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        side: THREE.DoubleSide
    });

    return new THREE.Mesh(tubeGeometry, material);
}

// Usage: rapidly regenerate the bolt for crackling effect
let boltMesh = null;
function updateLightning(scene, start, end, time) {
    if (boltMesh) scene.remove(boltMesh);
    if (Math.random() > 0.3) { // 70% chance to show bolt each frame = flickering
        boltMesh = createLightningBolt(start, end, 5);
        boltMesh.material.uniforms.uTime.value = time;
        scene.add(boltMesh);
    }
}
```

---

## 4. Shader-Based Psychic / Energy Effects

### 4.1 Concept

Psychic effects use:
- **Distortion / refraction** — warping the scene behind the effect
- **Chromatic aberration** — splitting RGB channels
- **Purple/pink energy fields** — noise-driven translucent volumes
- **Expanding rings** — shockwave distortion

### 4.2 Psychic Distortion Wave Shader

```glsl
// psychic_wave.frag — Expanding distortion shockwave
precision highp float;

uniform sampler2D uSceneTexture; // rendered scene as texture
uniform float uTime;
uniform vec2 uResolution;
uniform vec2 uImpactPoint;      // normalized impact position
uniform float uWaveProgress;    // 0.0 = hit moment, 1.0 = fully expanded
uniform float uIntensity;

void main() {
    vec2 uv = gl_FragCoord.xy / uResolution;
    vec2 center = uImpactPoint;

    float dist = distance(uv, center);

    // Wave ring parameters
    float waveRadius = uWaveProgress * 0.8;
    float waveWidth = 0.05 + uWaveProgress * 0.03;
    float waveFactor = smoothstep(waveRadius - waveWidth, waveRadius, dist) -
                       smoothstep(waveRadius, waveRadius + waveWidth, dist);

    // Distortion direction (radial from center)
    vec2 distortDir = normalize(uv - center);
    float distortAmount = waveFactor * 0.03 * uIntensity * (1.0 - uWaveProgress);

    // Chromatic aberration on the wave
    vec2 uvR = uv + distortDir * distortAmount * 1.2;
    vec2 uvG = uv + distortDir * distortAmount;
    vec2 uvB = uv + distortDir * distortAmount * 0.8;

    float r = texture2D(uSceneTexture, uvR).r;
    float g = texture2D(uSceneTexture, uvG).g;
    float b = texture2D(uSceneTexture, uvB).b;

    vec3 color = vec3(r, g, b);

    // Purple tint on wave
    vec3 psychicTint = vec3(0.6, 0.2, 0.8);
    color = mix(color, psychicTint, waveFactor * 0.3 * uIntensity);

    // Inner glow at impact point
    float innerGlow = exp(-dist * dist * 50.0) * (1.0 - uWaveProgress) * uIntensity;
    color += psychicTint * innerGlow;

    gl_FragColor = vec4(color, 1.0);
}
```

### 4.3 Purple Energy Field Shader

```glsl
// energy_field.frag — Swirling psychic energy around a pokemon
precision highp float;

uniform float uTime;
uniform vec2 uResolution;
uniform vec2 uCenter;
uniform float uRadius;
uniform float uIntensity;

// [include snoise, fbm from Section 1]

void main() {
    vec2 uv = gl_FragCoord.xy / uResolution;
    float aspect = uResolution.x / uResolution.y;
    uv.x *= aspect;
    vec2 center = uCenter * vec2(aspect, 1.0);

    float dist = length(uv - center);

    // Convert to polar
    vec2 delta = uv - center;
    float angle = atan(delta.y, delta.x);

    // Swirling noise in polar space
    float n1 = fbm(vec2(angle * 2.0 + uTime * 0.5, dist * 8.0 - uTime * 0.8));
    float n2 = fbm(vec2(angle * 3.0 - uTime * 0.3, dist * 6.0 + uTime * 0.5));

    // Field shape — stronger near uRadius, fading inward/outward
    float ring = 1.0 - abs(dist - uRadius) / (uRadius * 0.5);
    ring = clamp(ring, 0.0, 1.0);
    ring = pow(ring, 2.0);

    float field = ring * (n1 * 0.5 + 0.5) * (n2 * 0.5 + 0.5);
    field *= uIntensity;

    // Psychic color palette: deep purple -> magenta -> white
    vec3 color = vec3(0.3, 0.0, 0.5) * field;
    color += vec3(0.8, 0.2, 0.8) * pow(field, 2.0);
    color += vec3(1.0, 0.8, 1.0) * pow(field, 4.0);

    // Pulsing outer ring
    float pulse = sin(dist * 40.0 - uTime * 6.0) * 0.5 + 0.5;
    color += vec3(0.4, 0.1, 0.6) * pulse * ring * 0.2 * uIntensity;

    float alpha = clamp(field * 2.0, 0.0, 0.8);

    gl_FragColor = vec4(color, alpha);
}
```

### 4.4 Chromatic Aberration Post-Process Shader

```glsl
// chromatic_aberration.frag — Impact chromatic aberration
precision highp float;

uniform sampler2D tDiffuse;
uniform float uAmount;    // 0.0 = off, 0.02 = strong
uniform float uAngle;     // radial from impact point or fixed direction

varying vec2 vUv;

void main() {
    vec2 offset = uAmount * vec2(cos(uAngle), sin(uAngle));

    float r = texture2D(tDiffuse, vUv + offset).r;
    float g = texture2D(tDiffuse, vUv).g;
    float b = texture2D(tDiffuse, vUv - offset).b;
    float a = texture2D(tDiffuse, vUv).a;

    gl_FragColor = vec4(r, g, b, a);
}
```

> Based on Three.js RGBShiftShader pattern. Source: `three/examples/jsm/shaders/RGBShiftShader.js`

---

## 5. Post-Processing Impact Effects

### 5.1 EffectComposer Pipeline Setup

```javascript
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';

function setupPostProcessing(renderer, scene, camera) {
    const composer = new EffectComposer(renderer);

    // 1. Base render
    composer.addPass(new RenderPass(scene, camera));

    // 2. Bloom for glowing effects
    const bloomPass = new UnrealBloomPass(
        new THREE.Vector2(window.innerWidth, window.innerHeight),
        0.5,   // strength
        0.4,   // radius
        0.85   // threshold
    );
    composer.addPass(bloomPass);

    // 3. Custom impact effects (added dynamically)
    return { composer, bloomPass };
}
```

### 5.2 Radial Blur / Concentration Lines (Speed Lines)

```glsl
// radial_blur.frag — Manga-style concentration lines on impact
precision highp float;

uniform sampler2D tDiffuse;
uniform vec2 uCenter;      // blur center (normalized)
uniform float uStrength;   // 0.0 = off, 0.1 = strong
uniform int uSamples;      // 12 for good quality

varying vec2 vUv;

void main() {
    vec2 dir = vUv - uCenter;
    float dist = length(dir);
    dir = normalize(dir);

    vec4 color = vec4(0.0);
    float totalWeight = 0.0;

    for (int i = 0; i < 16; i++) {
        if (i >= uSamples) break;
        float t = float(i) / float(uSamples);
        float weight = 1.0 - t;
        vec2 sampleUV = vUv - dir * t * uStrength * dist;
        color += texture2D(tDiffuse, sampleUV) * weight;
        totalWeight += weight;
    }

    gl_FragColor = color / totalWeight;
}
```

**Three.js integration:**

```javascript
const RadialBlurShader = {
    uniforms: {
        tDiffuse: { value: null },
        uCenter: { value: new THREE.Vector2(0.5, 0.5) },
        uStrength: { value: 0.0 },
        uSamples: { value: 12 }
    },
    vertexShader: `
        varying vec2 vUv;
        void main() {
            vUv = uv;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
    `,
    fragmentShader: radialBlurFrag // from above
};

const radialBlurPass = new ShaderPass(RadialBlurShader);
composer.addPass(radialBlurPass);

// Trigger on impact:
function triggerRadialBlur(impactScreenPos, duration = 0.3) {
    radialBlurPass.uniforms.uCenter.value.copy(impactScreenPos);
    const startTime = performance.now();

    function animate() {
        const elapsed = (performance.now() - startTime) / 1000;
        const t = Math.min(elapsed / duration, 1.0);
        // Quick ramp up, slow fade
        radialBlurPass.uniforms.uStrength.value = Math.sin(t * Math.PI) * 0.08;
        if (t < 1.0) requestAnimationFrame(animate);
        else radialBlurPass.uniforms.uStrength.value = 0;
    }
    animate();
}
```

### 5.3 Screen Shake

```javascript
function screenShake(camera, intensity = 0.1, duration = 0.3, decay = true) {
    const originalPos = camera.position.clone();
    const startTime = performance.now();

    function shake() {
        const elapsed = (performance.now() - startTime) / 1000;
        if (elapsed > duration) {
            camera.position.copy(originalPos);
            return;
        }

        const factor = decay ? (1.0 - elapsed / duration) : 1.0;
        camera.position.x = originalPos.x + (Math.random() - 0.5) * intensity * factor;
        camera.position.y = originalPos.y + (Math.random() - 0.5) * intensity * factor;

        requestAnimationFrame(shake);
    }
    shake();
}
```

### 5.4 White Flash on Hit

```glsl
// white_flash.frag
precision highp float;

uniform sampler2D tDiffuse;
uniform float uFlashIntensity; // 0.0 = off, 1.0 = full white
uniform vec3 uFlashColor;      // vec3(1.0) for white, or type color

varying vec2 vUv;

void main() {
    vec4 color = texture2D(tDiffuse, vUv);
    color.rgb = mix(color.rgb, uFlashColor, uFlashIntensity);
    gl_FragColor = color;
}
```

### 5.5 Motion Blur Pass

```glsl
// motion_blur.frag — Velocity-based motion blur
precision highp float;

uniform sampler2D tDiffuse;
uniform vec2 uVelocity;    // screen-space velocity of the moving object
uniform float uStrength;

varying vec2 vUv;

void main() {
    vec4 color = vec4(0.0);
    int samples = 8;
    vec2 vel = uVelocity * uStrength;

    for (int i = 0; i < 8; i++) {
        float t = (float(i) / float(samples)) - 0.5;
        color += texture2D(tDiffuse, vUv + vel * t);
    }

    gl_FragColor = color / float(samples);
}
```

### 5.6 Bloom Settings by Type

```javascript
const TYPE_BLOOM_PRESETS = {
    fire:     { strength: 1.2, radius: 0.6, threshold: 0.3 },
    electric: { strength: 1.5, radius: 0.3, threshold: 0.2 },
    psychic:  { strength: 0.8, radius: 0.8, threshold: 0.4 },
    ice:      { strength: 0.6, radius: 0.5, threshold: 0.5 },
    dark:     { strength: 0.3, radius: 0.9, threshold: 0.7 },
    dragon:   { strength: 1.0, radius: 0.5, threshold: 0.3 },
    fairy:    { strength: 0.7, radius: 0.7, threshold: 0.4 },
    water:    { strength: 0.5, radius: 0.6, threshold: 0.5 },
    grass:    { strength: 0.4, radius: 0.5, threshold: 0.6 },
    normal:   { strength: 0.2, radius: 0.3, threshold: 0.8 }
};

function applyTypeBloom(bloomPass, type) {
    const preset = TYPE_BLOOM_PRESETS[type] || TYPE_BLOOM_PRESETS.normal;
    bloomPass.strength = preset.strength;
    bloomPass.radius = preset.radius;
    bloomPass.threshold = preset.threshold;
}
```

### 5.7 Luminosity High Pass Shader (for Bloom)

Used internally by UnrealBloomPass:

```glsl
// luminosity_highpass.frag
uniform sampler2D tDiffuse;
uniform vec3 defaultColor;
uniform float defaultOpacity;
uniform float luminosityThreshold;
uniform float smoothWidth;

varying vec2 vUv;

void main() {
    vec4 texel = texture2D(tDiffuse, vUv);
    float v = luminance(texel.xyz);
    vec4 outputColor = vec4(defaultColor.rgb, defaultOpacity);
    float alpha = smoothstep(luminosityThreshold, luminosityThreshold + smoothWidth, v);
    gl_FragColor = mix(outputColor, texel, alpha);
}
```

---

## 6. Sound Effects for Battle

### 6.1 Free Sound Sources

All URLs below are free for use under their respective licenses (Mixkit License, Pixabay License, Freesound CC0/CC-BY).

#### Fire Attacks
| Sound | Source |
|-------|--------|
| Short fire whoosh | `mixkit.co/free-sound-effects/fire/` — "Short fire whoosh" |
| Fire explosion | `mixkit.co/free-sound-effects/fire/` — "Fire explosion" |
| Fire spell with explosion | `mixkit.co/free-sound-effects/fire/` — "Fire spell with explosion" |
| Fireball spell | `mixkit.co/free-sound-effects/fire/` — "Fireball spell" |
| Wizard fire woosh | `mixkit.co/free-sound-effects/fire/` — "Wizard fire woosh" |
| Big fire magic swoosh | `mixkit.co/free-sound-effects/fire/` — "Big fire magic swoosh" |
| Intense long fire beam | `mixkit.co/free-sound-effects/fire/` — "Intense long fire beam" |
| Aggressive fire flame | `mixkit.co/free-sound-effects/fire/` — "Aggressive fire flame" |

#### Ice Attacks
| Sound | Source |
|-------|--------|
| Icicles spell whoosh | `mixkit.co/free-sound-effects/magic/` — "Icicles spell whoosh" |
| Glass break / ice shatter | `mixkit.co/free-sound-effects/glass/` — search for "glass shatter" |
| Freeze crystal | `freesound.org` — search "ice crystal", filter CC0 |
| Wind chill | `mixkit.co/free-sound-effects/wind/` — cold wind sounds |

#### Electric / Thunder
| Sound | Source |
|-------|--------|
| Fast thunder whoosh | `mixkit.co/free-sound-effects/thunder/` — "Fast thunder whoosh" |
| Electric storm thunder | `mixkit.co/free-sound-effects/thunder/` — "Electric storm thunder" |
| Close explosion thunder | `mixkit.co/free-sound-effects/thunder/` — "Close explosion thunder" |
| Cinematic impact thunder | `mixkit.co/free-sound-effects/thunder/` — "Cinematic impact thunder" |
| Strong close thunder explosion | `mixkit.co/free-sound-effects/thunder/` — "Strong close thunder explosion" |
| Cinematic thunder | `mixkit.co/free-sound-effects/thunder/` — "Cinematic thunder" |

#### Psychic / Ethereal
| Sound | Source |
|-------|--------|
| Magic astral sweep | `mixkit.co/free-sound-effects/magic/` — "Magic astral sweep effect" |
| Magical light aura | `mixkit.co/free-sound-effects/magic/` — "Magical light aura" |
| Magic spell mystery whoosh | `mixkit.co/free-sound-effects/magic/` — "Magic spell mystery whoosh" |
| Casting long fairy magic spell | `mixkit.co/free-sound-effects/magic/` — "Casting long fairy magic spell" |
| Shot light energy flowing | `mixkit.co/free-sound-effects/magic/` — "Shot light energy flowing" |
| Spellcaster fairy swoosh | `mixkit.co/free-sound-effects/magic/` — "Spellcaster fairy swoosh" |

#### Dark / Ominous
| Sound | Source |
|-------|--------|
| Dark ambient whoosh | `freesound.org` — search "dark whoosh" CC0 |
| Ominous pulse | `freesound.org` — search "ominous pulse" CC0 |
| Deep rumble bass | `mixkit.co/free-sound-effects/thunder/` — "Thunder deep rumble" |
| Big thunder rumble | `mixkit.co/free-sound-effects/thunder/` — "Big thunder rumble" |

#### Impact / Hit
| Sound | Source |
|-------|--------|
| Big cinematic impact | `mixkit.co/free-sound-effects/hit/` — "Big cinematic impact" |
| Martial arts fast punch | `mixkit.co/free-sound-effects/hit/` — "Martial arts fast punch" |
| Body cutting impact | `mixkit.co/free-sound-effects/hit/` — "Body cutting impact" |
| Quick ninja strike | `mixkit.co/free-sound-effects/hit/` — "Quick ninja strike" |
| Strong punches to the body | `mixkit.co/free-sound-effects/hit/` — "Strong punches to the body" |

#### Pokeball
| Sound | Source |
|-------|--------|
| Throw whoosh | `mixkit.co/free-sound-effects/whoosh/` — search short whoosh |
| Ball open flash | `mixkit.co/free-sound-effects/magic/` — "Light spell" |
| Materialization | `mixkit.co/free-sound-effects/magic/` — "Fairy sparkle whoosh" |

#### Crowd / Spectators
| Sound | Source |
|-------|--------|
| Huge crowd cheering victory | `mixkit.co/free-sound-effects/crowd/` — "Huge crowd cheering victory" |
| Stadium joy shouting crowd | `mixkit.co/free-sound-effects/crowd/` — "Stadium joy shouting crowd" |
| Ending show audience clapping | `mixkit.co/free-sound-effects/crowd/` — "Ending show audience clapping" |
| Crowd gasp | `freesound.org` — search "crowd gasp" CC0 |

#### Background Music / Ambience
| Sound | Source |
|-------|--------|
| Battle BGM | `pixabay.com/music/` — search "battle" or "epic game" (Pixabay License, free) |
| Arena ambience | `freesound.org` — search "arena ambience" CC0 |

### 6.2 Recommended Freesound.org Search Queries

Freesound.org allows filtering by CC0 license for completely free use:

```
# Fire
https://freesound.org/search/?q=fire+whoosh&f=license:%22Creative+Commons+0%22

# Ice / Crystal
https://freesound.org/search/?q=ice+crystal+freeze&f=license:%22Creative+Commons+0%22

# Thunder / Electric
https://freesound.org/search/?q=electric+zap+spark&f=license:%22Creative+Commons+0%22

# Psychic / Ethereal
https://freesound.org/search/?q=ethereal+hum+psychic&f=license:%22Creative+Commons+0%22

# Dark / Ominous
https://freesound.org/search/?q=dark+ominous+pulse&f=license:%22Creative+Commons+0%22

# Impact
https://freesound.org/search/?q=punch+impact+hit&f=license:%22Creative+Commons+0%22

# Crowd
https://freesound.org/search/?q=crowd+cheer+gasp&f=license:%22Creative+Commons+0%22

# Pokeball-like
https://freesound.org/search/?q=capsule+open+flash&f=license:%22Creative+Commons+0%22
```

---

## 7. Howler.js Integration

### 7.1 Setup

```html
<script src="https://cdnjs.cloudflare.com/ajax/libs/howler/2.2.4/howler.min.js"></script>
```

Or via npm:
```bash
npm install howler
```

### 7.2 Audio Sprite System for Battle SFX

Audio sprites pack multiple sounds into one file = fewer HTTP requests, faster loading.

```javascript
// battle_audio.js — Central audio manager
const battleSFX = new Howl({
    src: ['assets/audio/battle_sfx_sprite.webm', 'assets/audio/battle_sfx_sprite.mp3'],
    sprite: {
        // name:   [offset_ms, duration_ms]
        fire_whoosh:       [0,     800],
        fire_explosion:    [1000,  1200],
        fire_beam:         [2500,  2000],
        ice_freeze:        [5000,  1000],
        ice_shatter:       [6200,  800],
        electric_zap:      [7200,  600],
        electric_thunder:  [8000,  1500],
        electric_crackle:  [9800,  1000],
        psychic_wave:      [11000, 1200],
        psychic_hum:       [12500, 2000],
        dark_pulse:        [15000, 1500],
        dark_ominous:      [16800, 2000],
        impact_light:      [19000, 400],
        impact_heavy:      [19600, 600],
        impact_critical:   [20400, 1000],
        pokeball_throw:    [21600, 500],
        pokeball_open:     [22300, 800],
        pokeball_capture:  [23300, 1200],
        materialize:       [24700, 1000],
        crowd_cheer:       [26000, 3000],
        crowd_gasp:        [29200, 1500],
        crowd_applause:    [31000, 4000],
        ko_thud:           [35200, 800],
        victory_fanfare:   [36200, 3000]
    },
    volume: 0.7
});

// Type-specific attack sound mapping
const TYPE_SOUNDS = {
    fire:     { charge: 'fire_whoosh',      hit: 'fire_explosion',    beam: 'fire_beam' },
    water:    { charge: 'psychic_wave',     hit: 'impact_heavy',      beam: 'ice_freeze' },
    electric: { charge: 'electric_crackle', hit: 'electric_thunder',  beam: 'electric_zap' },
    ice:      { charge: 'ice_freeze',       hit: 'ice_shatter',       beam: 'ice_freeze' },
    psychic:  { charge: 'psychic_hum',      hit: 'psychic_wave',      beam: 'psychic_hum' },
    dark:     { charge: 'dark_ominous',     hit: 'dark_pulse',        beam: 'dark_pulse' },
    normal:   { charge: 'impact_light',     hit: 'impact_heavy',      beam: 'impact_light' },
    dragon:   { charge: 'fire_whoosh',      hit: 'fire_explosion',    beam: 'fire_beam' },
    fairy:    { charge: 'psychic_wave',     hit: 'materialize',       beam: 'psychic_hum' }
};
```

### 7.3 Playback Control

```javascript
class BattleAudioManager {
    constructor() {
        this.sfx = battleSFX;
        this.bgm = null;
        this.currentBGMId = null;
        this.masterVolume = 1.0;
    }

    // Play a type-specific attack sound
    playAttack(type, phase) {
        const sounds = TYPE_SOUNDS[type] || TYPE_SOUNDS.normal;
        const spriteKey = sounds[phase]; // 'charge', 'hit', or 'beam'
        if (spriteKey) {
            return this.sfx.play(spriteKey);
        }
    }

    // Play with fade-in
    playWithFade(spriteKey, fadeMs = 300) {
        const id = this.sfx.play(spriteKey);
        this.sfx.fade(0, this.masterVolume, fadeMs, id);
        return id;
    }

    // Stop with fade-out
    stopWithFade(id, fadeMs = 300) {
        this.sfx.fade(this.sfx.volume(undefined, id), 0, fadeMs, id);
        setTimeout(() => this.sfx.stop(id), fadeMs);
    }

    // Impact sound with screen shake sync
    playImpact(severity = 'normal') {
        const map = { light: 'impact_light', normal: 'impact_heavy', critical: 'impact_critical' };
        return this.sfx.play(map[severity]);
    }

    // Background music
    startBGM(src, volume = 0.3) {
        if (this.bgm) this.bgm.unload();
        this.bgm = new Howl({
            src: [src],
            loop: true,
            volume: 0
        });
        this.currentBGMId = this.bgm.play();
        this.bgm.fade(0, volume, 2000, this.currentBGMId);
    }

    stopBGM(fadeMs = 2000) {
        if (this.bgm && this.currentBGMId !== null) {
            this.bgm.fade(this.bgm.volume(), 0, fadeMs, this.currentBGMId);
            setTimeout(() => { this.bgm.stop(); }, fadeMs);
        }
    }

    // Crowd reactions
    playCrowdReaction(reaction) {
        // reaction: 'cheer', 'gasp', 'applause'
        return this.sfx.play(`crowd_${reaction}`);
    }

    setMasterVolume(v) {
        this.masterVolume = v;
        Howler.volume(v);
    }
}
```

### 7.4 Spatial Audio for Arena Feel

```javascript
// Positional audio — left/right panning based on pokemon position
function playSpatialSFX(audioManager, spriteKey, panX) {
    // panX: -1.0 (left) to 1.0 (right)
    const id = audioManager.sfx.play(spriteKey);
    audioManager.sfx.stereo(panX, id);
    return id;
}

// Attacker on left, defender on right
function playAttackSequence(audioManager, type, attackerSide) {
    const pan = attackerSide === 'left' ? -0.6 : 0.6;
    const targetPan = -pan;

    // Charge sound at attacker position
    const chargeId = playSpatialSFX(audioManager, TYPE_SOUNDS[type].charge, pan);

    // After charge, hit sound at target position
    setTimeout(() => {
        playSpatialSFX(audioManager, TYPE_SOUNDS[type].hit, targetPan);
        playSpatialSFX(audioManager, 'impact_heavy', targetPan);
    }, 600);
}
```

### 7.5 Creating Audio Sprites

Use `audiosprite` CLI tool to merge individual sound files into a single sprite:

```bash
npm install -g audiosprite
audiosprite -o battle_sfx_sprite -f howler \
    fire_whoosh.wav fire_explosion.wav fire_beam.wav \
    ice_freeze.wav ice_shatter.wav \
    electric_zap.wav electric_thunder.wav electric_crackle.wav \
    psychic_wave.wav psychic_hum.wav \
    dark_pulse.wav dark_ominous.wav \
    impact_light.wav impact_heavy.wav impact_critical.wav \
    pokeball_throw.wav pokeball_open.wav pokeball_capture.wav \
    materialize.wav \
    crowd_cheer.wav crowd_gasp.wav crowd_applause.wav \
    ko_thud.wav victory_fanfare.wav
```

This generates `battle_sfx_sprite.webm`, `.mp3`, and a JSON sprite map.

---

## 8. Pokeball Animation

### 8.1 Animation Sequence

1. **Throw Arc** (0.0s - 0.6s): Pokeball follows a parabolic arc from trainer to pokemon
2. **Spin** (during throw): Ball rotates on its z-axis, 720 degrees
3. **Open Flash** (0.6s - 0.8s): Ball halves separate, blinding white light emanates
4. **Energy Beam** (0.8s - 1.2s): Red/white energy beam connects ball to materialization point
5. **Materialization** (1.2s - 2.0s): Pokemon forms from energy particles, top to bottom
6. **Ball Recall** (if returning): Reverse — pokemon dissolves into beam back to ball

### 8.2 Pokeball 3D Model (Procedural)

```javascript
function createPokeball() {
    const group = new THREE.Group();

    // Bottom half (white)
    const bottomGeom = new THREE.SphereGeometry(0.5, 32, 16, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2);
    const bottomMat = new THREE.MeshStandardMaterial({ color: 0xeeeeee, metalness: 0.3, roughness: 0.4 });
    const bottom = new THREE.Mesh(bottomGeom, bottomMat);
    group.add(bottom);

    // Top half (red)
    const topGeom = new THREE.SphereGeometry(0.5, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2);
    const topMat = new THREE.MeshStandardMaterial({ color: 0xcc0000, metalness: 0.3, roughness: 0.4 });
    const top = new THREE.Mesh(topGeom, topMat);
    group.add(top);

    // Center band (black ring)
    const bandGeom = new THREE.TorusGeometry(0.5, 0.03, 8, 32);
    const bandMat = new THREE.MeshStandardMaterial({ color: 0x222222 });
    const band = new THREE.Mesh(bandGeom, bandMat);
    band.rotation.x = Math.PI / 2;
    group.add(band);

    // Center button
    const buttonGeom = new THREE.SphereGeometry(0.08, 16, 16);
    const buttonMat = new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 0.3 });
    const button = new THREE.Mesh(buttonGeom, buttonMat);
    button.position.z = 0.49;
    group.add(button);

    group.scale.setScalar(0.15); // scale to scene proportions

    return { group, top, bottom, button };
}
```

### 8.3 Throw Animation (GSAP or manual)

```javascript
function animatePokeballThrow(pokeball, startPos, targetPos, onComplete) {
    const duration = 600; // ms
    const startTime = performance.now();
    const arcHeight = 2.0;

    // Calculate arc
    const midY = Math.max(startPos.y, targetPos.y) + arcHeight;

    function animate() {
        const elapsed = performance.now() - startTime;
        const t = Math.min(elapsed / duration, 1.0);

        // Parabolic arc: x/z linear, y parabolic
        pokeball.group.position.x = THREE.MathUtils.lerp(startPos.x, targetPos.x, t);
        pokeball.group.position.z = THREE.MathUtils.lerp(startPos.z, targetPos.z, t);

        // Quadratic Bezier for y
        const y1 = THREE.MathUtils.lerp(startPos.y, midY, t);
        const y2 = THREE.MathUtils.lerp(midY, targetPos.y, t);
        pokeball.group.position.y = THREE.MathUtils.lerp(y1, y2, t);

        // Spin
        pokeball.group.rotation.z += 0.3;
        pokeball.group.rotation.x += 0.1;

        // Scale bounce at end
        if (t > 0.9) {
            const bounce = 1.0 + Math.sin((t - 0.9) / 0.1 * Math.PI) * 0.2;
            pokeball.group.scale.setScalar(0.15 * bounce);
        }

        if (t < 1.0) {
            requestAnimationFrame(animate);
        } else {
            onComplete();
        }
    }
    animate();
}
```

### 8.4 Open Animation with Energy Release

```javascript
function animatePokeballOpen(pokeball, scene, onMaterialize) {
    const duration = 400;
    const startTime = performance.now();

    // Add point light for flash
    const flash = new THREE.PointLight(0xffffff, 0, 5);
    flash.position.copy(pokeball.group.position);
    scene.add(flash);

    // Energy particles
    const particleCount = 50;
    const particleGeom = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    const velocities = [];

    for (let i = 0; i < particleCount; i++) {
        positions[i * 3] = pokeball.group.position.x;
        positions[i * 3 + 1] = pokeball.group.position.y;
        positions[i * 3 + 2] = pokeball.group.position.z;
        velocities.push(new THREE.Vector3(
            (Math.random() - 0.5) * 4,
            Math.random() * 3,
            (Math.random() - 0.5) * 4
        ));
    }
    particleGeom.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    const particleMat = new THREE.PointsMaterial({
        color: 0xffffff,
        size: 0.1,
        transparent: true,
        blending: THREE.AdditiveBlending
    });
    const particles = new THREE.Points(particleGeom, particleMat);
    scene.add(particles);

    function animate() {
        const elapsed = performance.now() - startTime;
        const t = Math.min(elapsed / duration, 1.0);

        // Separate ball halves
        pokeball.top.position.y = t * 0.3;
        pokeball.top.rotation.x = -t * 0.5;
        pokeball.bottom.position.y = -t * 0.1;

        // Flash intensity
        flash.intensity = Math.sin(t * Math.PI) * 10;

        // Button glow
        pokeball.button.material.emissiveIntensity = 1.0 + Math.sin(t * Math.PI) * 5;

        // Particle expansion
        const posArr = particles.geometry.attributes.position.array;
        for (let i = 0; i < particleCount; i++) {
            posArr[i * 3]     += velocities[i].x * 0.02;
            posArr[i * 3 + 1] += velocities[i].y * 0.02;
            posArr[i * 3 + 2] += velocities[i].z * 0.02;
        }
        particles.geometry.attributes.position.needsUpdate = true;
        particleMat.opacity = 1.0 - t;

        if (t < 1.0) {
            requestAnimationFrame(animate);
        } else {
            scene.remove(flash);
            scene.remove(particles);
            scene.remove(pokeball.group);
            onMaterialize();
        }
    }
    animate();
}
```

### 8.5 Pokemon Materialization Shader

```glsl
// materialize.frag — Dissolve-in effect
precision highp float;

uniform sampler2D uPokemonTexture;
uniform float uProgress;    // 0.0 = invisible, 1.0 = fully visible
uniform vec3 uEnergyColor;  // type color for the energy

varying vec2 vUv;

// [include snoise from Section 1]

void main() {
    vec4 texColor = texture2D(uPokemonTexture, vUv);

    // Dissolve threshold based on vertical position + noise
    float noise = snoise(vUv * 10.0) * 0.3;
    float threshold = vUv.y + noise; // materialize bottom-to-top

    // Compare with progress
    float visible = smoothstep(uProgress - 0.1, uProgress, threshold);

    if (visible > 0.99) {
        // Fully materialized pixel
        gl_FragColor = texColor;
    } else if (visible > 0.01) {
        // Edge glow — energy color at the materialization boundary
        float edgeGlow = 1.0 - visible;
        vec3 glow = uEnergyColor * edgeGlow * 3.0;
        gl_FragColor = vec4(texColor.rgb + glow, texColor.a);
    } else {
        // Not yet materialized — show energy particles
        float energyNoise = snoise(vUv * 20.0 + vec2(0.0, uProgress * 5.0));
        float energy = smoothstep(0.3, 0.5, energyNoise) * (1.0 - uProgress);
        gl_FragColor = vec4(uEnergyColor * energy * 2.0, energy * 0.5);
    }
}
```

---

## 9. Crowd / Spectator System

### 9.1 InstancedMesh for Many Spectators

Render hundreds of spectators with a single draw call using `InstancedMesh`.

```javascript
function createCrowd(scene, count = 500, arenaRadius = 15) {
    // Simple spectator geometry (low-poly capsule)
    const bodyGeom = new THREE.CapsuleGeometry(0.15, 0.4, 4, 8);
    const headGeom = new THREE.SphereGeometry(0.1, 8, 8);

    // Merge body + head for single geometry
    const mergedGeom = new THREE.BufferGeometry();
    // In practice, use BufferGeometryUtils.mergeGeometries:
    // import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

    const material = new THREE.MeshLambertMaterial();

    const crowd = new THREE.InstancedMesh(bodyGeom, material, count);
    const dummy = new THREE.Object3D();
    const colors = new Float32Array(count * 3);

    for (let i = 0; i < count; i++) {
        // Arrange in stadium-style rows
        const row = Math.floor(i / 60);
        const seat = i % 60;
        const angle = (seat / 60) * Math.PI * 2;
        const radius = arenaRadius + row * 0.8;
        const height = row * 0.5 + 0.3;

        dummy.position.set(
            Math.cos(angle) * radius,
            height,
            Math.sin(angle) * radius
        );
        // Face center
        dummy.lookAt(0, height, 0);
        dummy.updateMatrix();
        crowd.setMatrixAt(i, dummy.matrix);

        // Random shirt colors
        const color = new THREE.Color();
        color.setHSL(Math.random(), 0.6, 0.5);
        colors[i * 3]     = color.r;
        colors[i * 3 + 1] = color.g;
        colors[i * 3 + 2] = color.b;
    }

    crowd.instanceMatrix.needsUpdate = true;

    // Per-instance colors
    crowd.instanceColor = new THREE.InstancedBufferAttribute(colors, 3);
    crowd.instanceColor.needsUpdate = true;

    scene.add(crowd);
    return { mesh: crowd, dummy, count };
}
```

### 9.2 Crowd Reaction Animations

```javascript
class CrowdAnimator {
    constructor(crowdData) {
        this.crowd = crowdData;
        this.baseMatrices = [];
        this.reactionState = new Float32Array(crowdData.count); // 0 = idle

        // Store base positions
        const mat = new THREE.Matrix4();
        for (let i = 0; i < crowdData.count; i++) {
            crowdData.mesh.getMatrixAt(i, mat);
            this.baseMatrices.push(mat.clone());
        }
    }

    // Make crowd jump and cheer
    triggerCheer(duration = 2.0) {
        const startTime = performance.now();
        for (let i = 0; i < this.crowd.count; i++) {
            // Stagger: random delay per spectator
            this.reactionState[i] = Math.random() * 0.3;
        }

        const animate = () => {
            const elapsed = (performance.now() - startTime) / 1000;
            if (elapsed > duration) {
                this._resetPositions();
                return;
            }

            const dummy = this.crowd.dummy;
            for (let i = 0; i < this.crowd.count; i++) {
                const delay = this.reactionState[i];
                const t = Math.max(0, elapsed - delay);
                if (t <= 0) continue;

                const baseMat = this.baseMatrices[i];
                dummy.position.setFromMatrixPosition(baseMat);

                // Jump motion
                const jumpPhase = Math.sin(t * 8.0) * Math.exp(-t * 2.0);
                dummy.position.y += jumpPhase * 0.3;

                // Arm raise (rotation)
                dummy.rotation.setFromRotationMatrix(baseMat);
                dummy.rotation.z += jumpPhase * 0.2;

                dummy.updateMatrix();
                this.crowd.mesh.setMatrixAt(i, dummy.matrix);
            }
            this.crowd.mesh.instanceMatrix.needsUpdate = true;
            requestAnimationFrame(animate);
        };
        animate();
    }

    // Gasp: lean forward slightly
    triggerGasp() {
        const dummy = this.crowd.dummy;
        for (let i = 0; i < this.crowd.count; i++) {
            const baseMat = this.baseMatrices[i];
            dummy.position.setFromMatrixPosition(baseMat);
            dummy.rotation.setFromRotationMatrix(baseMat);
            dummy.rotation.x += 0.15; // lean forward
            dummy.updateMatrix();
            this.crowd.mesh.setMatrixAt(i, dummy.matrix);
        }
        this.crowd.mesh.instanceMatrix.needsUpdate = true;

        // Reset after 1 second
        setTimeout(() => this._resetPositions(), 1000);
    }

    // Idle animation (subtle swaying)
    updateIdle(time) {
        const dummy = this.crowd.dummy;
        for (let i = 0; i < this.crowd.count; i++) {
            const baseMat = this.baseMatrices[i];
            dummy.position.setFromMatrixPosition(baseMat);
            dummy.rotation.setFromRotationMatrix(baseMat);

            // Very subtle sway
            const phase = i * 0.1 + time;
            dummy.position.y += Math.sin(phase) * 0.02;
            dummy.rotation.z = Math.sin(phase * 0.5) * 0.03;

            dummy.updateMatrix();
            this.crowd.mesh.setMatrixAt(i, dummy.matrix);
        }
        this.crowd.mesh.instanceMatrix.needsUpdate = true;
    }

    _resetPositions() {
        for (let i = 0; i < this.crowd.count; i++) {
            this.crowd.mesh.setMatrixAt(i, this.baseMatrices[i]);
        }
        this.crowd.mesh.instanceMatrix.needsUpdate = true;
    }
}
```

### 9.3 Billboard Sprite Spectators (Alternative)

For even cheaper rendering, use textured quads that always face the camera:

```javascript
function createBillboardCrowd(scene, count = 1000, arenaRadius = 15) {
    const textureLoader = new THREE.TextureLoader();
    const spectatorTexture = textureLoader.load('assets/spectator_sprite.png');

    const geometry = new THREE.PlaneGeometry(0.3, 0.5);
    const material = new THREE.MeshBasicMaterial({
        map: spectatorTexture,
        transparent: true,
        alphaTest: 0.5,
        side: THREE.DoubleSide
    });

    const crowd = new THREE.InstancedMesh(geometry, material, count);
    const dummy = new THREE.Object3D();

    for (let i = 0; i < count; i++) {
        const row = Math.floor(i / 80);
        const seat = i % 80;
        const angle = (seat / 80) * Math.PI * 2;
        const radius = arenaRadius + row * 0.6;

        dummy.position.set(
            Math.cos(angle) * radius,
            row * 0.4 + 0.25,
            Math.sin(angle) * radius
        );
        dummy.lookAt(0, dummy.position.y, 0); // face center
        dummy.updateMatrix();
        crowd.setMatrixAt(i, dummy.matrix);
    }

    crowd.instanceMatrix.needsUpdate = true;
    scene.add(crowd);
    return crowd;
}
```

---

## 10. Trainer Models

### 10.1 Simple Procedural Trainer

```javascript
function createTrainer(color = 0x3366cc) {
    const group = new THREE.Group();

    // Body
    const body = new THREE.Mesh(
        new THREE.CapsuleGeometry(0.2, 0.6, 4, 12),
        new THREE.MeshStandardMaterial({ color })
    );
    body.position.y = 0.7;
    group.add(body);

    // Head
    const head = new THREE.Mesh(
        new THREE.SphereGeometry(0.15, 12, 12),
        new THREE.MeshStandardMaterial({ color: 0xffccaa }) // skin
    );
    head.position.y = 1.25;
    group.add(head);

    // Hat (cap)
    const hat = new THREE.Mesh(
        new THREE.CylinderGeometry(0.18, 0.16, 0.08, 12),
        new THREE.MeshStandardMaterial({ color: 0xcc0000 })
    );
    hat.position.y = 1.38;
    group.add(hat);

    // Hat brim
    const brim = new THREE.Mesh(
        new THREE.CylinderGeometry(0.22, 0.22, 0.02, 12),
        new THREE.MeshStandardMaterial({ color: 0xcc0000 })
    );
    brim.position.y = 1.34;
    brim.position.z = 0.05;
    group.add(brim);

    // Arms
    [-1, 1].forEach(side => {
        const arm = new THREE.Mesh(
            new THREE.CapsuleGeometry(0.06, 0.4, 4, 8),
            new THREE.MeshStandardMaterial({ color })
        );
        arm.position.set(side * 0.28, 0.8, 0);
        arm.rotation.z = side * 0.2;
        group.add(arm);
    });

    // Legs
    [-1, 1].forEach(side => {
        const leg = new THREE.Mesh(
            new THREE.CapsuleGeometry(0.08, 0.35, 4, 8),
            new THREE.MeshStandardMaterial({ color: 0x333344 })
        );
        leg.position.set(side * 0.12, 0.2, 0);
        group.add(leg);
    });

    return group;
}
```

### 10.2 Trainer Animation

```javascript
class TrainerAnimator {
    constructor(trainerGroup) {
        this.group = trainerGroup;
        this.arms = trainerGroup.children.filter(c =>
            c.position.x !== 0 && c.geometry.type === 'CapsuleGeometry' && c.position.y > 0.5
        );
    }

    // Idle breathing
    idle(time) {
        this.group.position.y = Math.sin(time * 2) * 0.01;
    }

    // Throw pokeball gesture
    throwPose(progress) {
        // progress: 0 = wind up, 0.5 = throw, 1 = follow through
        if (this.arms.length >= 2) {
            const rightArm = this.arms[1];
            if (progress < 0.5) {
                // Wind up — arm goes back
                rightArm.rotation.z = -0.5 - progress * 2.0;
                rightArm.rotation.x = -progress * 1.0;
            } else {
                // Throw forward
                const t = (progress - 0.5) * 2;
                rightArm.rotation.z = -1.5 + t * 2.0;
                rightArm.rotation.x = -0.5 + t * 1.5;
            }
        }
    }

    // Victory pose
    victory(time) {
        this.arms.forEach((arm, i) => {
            arm.rotation.z = (i === 0 ? -1 : 1) * (1.2 + Math.sin(time * 3) * 0.2);
        });
        this.group.position.y = Math.abs(Math.sin(time * 4)) * 0.1; // jumping
    }

    // Defeat pose (slouch)
    defeat(progress) {
        this.group.rotation.x = progress * 0.3; // lean forward
        this.group.position.y = -progress * 0.1; // sink
    }
}
```

### 10.3 Sprite-Based Trainer (Alternative)

For a 2D sprite approach using a textured plane:

```javascript
function createSpriteTrainer(texturePath) {
    const texture = new THREE.TextureLoader().load(texturePath);
    texture.magFilter = THREE.NearestFilter; // pixel-art style
    texture.minFilter = THREE.NearestFilter;

    const material = new THREE.SpriteMaterial({
        map: texture,
        transparent: true
    });

    const sprite = new THREE.Sprite(material);
    sprite.scale.set(1.0, 1.5, 1.0);
    sprite.position.y = 0.75;

    return sprite;
}
```

---

## 11. Three.js ShaderMaterial Patterns

### 11.1 Basic ShaderMaterial Setup (r170+)

```javascript
const material = new THREE.ShaderMaterial({
    uniforms: {
        uTime:       { value: 0.0 },
        uResolution: { value: new THREE.Vector2(window.innerWidth, window.innerHeight) },
        uColor:      { value: new THREE.Color(0xff0000) },
        uTexture:    { value: someTexture },
        uMouse:      { value: new THREE.Vector2(0, 0) },
        uIntensity:  { value: 1.0 }
    },
    vertexShader: `
        varying vec2 vUv;
        varying vec3 vPosition;
        varying vec3 vNormal;

        void main() {
            vUv = uv;
            vPosition = position;
            vNormal = normalMatrix * normal;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
    `,
    fragmentShader: `
        uniform float uTime;
        uniform vec2 uResolution;
        uniform vec3 uColor;
        varying vec2 vUv;

        void main() {
            // Your effect here
            gl_FragColor = vec4(uColor, 1.0);
        }
    `,
    transparent: true,
    blending: THREE.AdditiveBlending, // or NormalBlending
    depthWrite: false,                // for transparent/additive effects
    side: THREE.DoubleSide
});
```

### 11.2 Custom Particle System with ShaderMaterial

```javascript
function createShaderParticleSystem(scene, count = 5000) {
    const geometry = new THREE.BufferGeometry();

    // Per-particle attributes
    const positions   = new Float32Array(count * 3);
    const randomness  = new Float32Array(count * 3);  // random seed per particle
    const sizes       = new Float32Array(count);
    const lifetimes   = new Float32Array(count);

    for (let i = 0; i < count; i++) {
        positions[i * 3]     = (Math.random() - 0.5) * 10;
        positions[i * 3 + 1] = Math.random() * 5;
        positions[i * 3 + 2] = (Math.random() - 0.5) * 10;
        randomness[i * 3]     = Math.random();
        randomness[i * 3 + 1] = Math.random();
        randomness[i * 3 + 2] = Math.random();
        sizes[i] = 1.0 + Math.random() * 5.0;
        lifetimes[i] = Math.random();
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('aRandom', new THREE.BufferAttribute(randomness, 3));
    geometry.setAttribute('aSize', new THREE.BufferAttribute(sizes, 1));
    geometry.setAttribute('aLifetime', new THREE.BufferAttribute(lifetimes, 1));

    const material = new THREE.ShaderMaterial({
        uniforms: {
            uTime: { value: 0 },
            uPixelRatio: { value: Math.min(window.devicePixelRatio, 2) },
            uColor1: { value: new THREE.Color('#ff6600') },
            uColor2: { value: new THREE.Color('#ffcc00') },
            uPointTexture: { value: createCircleTexture() }
        },
        vertexShader: `
            attribute vec3 aRandom;
            attribute float aSize;
            attribute float aLifetime;

            uniform float uTime;
            uniform float uPixelRatio;

            varying float vLife;
            varying float vIntensity;

            void main() {
                float t = fract(aLifetime + uTime * 0.2);
                vLife = 1.0 - t;
                vIntensity = aRandom.z;

                vec3 pos = position;

                // Animate: spiral upward
                float angle = t * 6.28 * aRandom.x * 3.0 + aRandom.y * 6.28;
                float radius = aRandom.x * 2.0 * (1.0 - t);
                pos.x += cos(angle) * radius;
                pos.z += sin(angle) * radius;
                pos.y += t * 5.0 * (0.5 + aRandom.y);

                vec4 mvPos = modelViewMatrix * vec4(pos, 1.0);
                gl_PointSize = aSize * vLife * uPixelRatio * (300.0 / -mvPos.z);
                gl_Position = projectionMatrix * mvPos;
            }
        `,
        fragmentShader: `
            uniform vec3 uColor1;
            uniform vec3 uColor2;
            uniform sampler2D uPointTexture;

            varying float vLife;
            varying float vIntensity;

            void main() {
                vec4 texColor = texture2D(uPointTexture, gl_PointCoord);
                if (texColor.a < 0.1) discard;

                vec3 color = mix(uColor1, uColor2, vIntensity);
                float alpha = texColor.a * vLife;

                gl_FragColor = vec4(color * (1.0 + vLife), alpha);
            }
        `,
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false
    });

    const points = new THREE.Points(geometry, material);
    scene.add(points);
    return { mesh: points, material };
}

// Helper: create a soft circle texture for particles
function createCircleTexture(size = 64) {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = size;
    const ctx = canvas.getContext('2d');
    const gradient = ctx.createRadialGradient(size/2, size/2, 0, size/2, size/2, size/2);
    gradient.addColorStop(0, 'rgba(255,255,255,1)');
    gradient.addColorStop(0.3, 'rgba(255,255,255,0.8)');
    gradient.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, size, size);
    const texture = new THREE.CanvasTexture(canvas);
    return texture;
}
```

### 11.3 Type-Specific Particle Color Presets

```javascript
const TYPE_PARTICLE_COLORS = {
    fire:     { c1: '#ff4400', c2: '#ffcc00', c3: '#ff8800' },
    water:    { c1: '#0066ff', c2: '#88ccff', c3: '#0044aa' },
    electric: { c1: '#ffff00', c2: '#ffffff', c3: '#ffaa00' },
    grass:    { c1: '#22cc22', c2: '#88ff44', c3: '#116611' },
    ice:      { c1: '#aaddff', c2: '#ffffff', c3: '#66bbee' },
    psychic:  { c1: '#cc44ff', c2: '#ff88cc', c3: '#8800aa' },
    dark:     { c1: '#442244', c2: '#884466', c3: '#220022' },
    dragon:   { c1: '#6644cc', c2: '#ff4444', c3: '#4422aa' },
    fairy:    { c1: '#ff88cc', c2: '#ffccee', c3: '#ee66aa' },
    fighting: { c1: '#cc4422', c2: '#ff8844', c3: '#882211' },
    poison:   { c1: '#aa44cc', c2: '#cc88dd', c3: '#662288' },
    ground:   { c1: '#cc9944', c2: '#eebb66', c3: '#886622' },
    flying:   { c1: '#8899ee', c2: '#bbccff', c3: '#6677cc' },
    bug:      { c1: '#88aa22', c2: '#bbcc44', c3: '#667711' },
    rock:     { c1: '#aa9966', c2: '#ccbb88', c3: '#887744' },
    ghost:    { c1: '#664488', c2: '#9966cc', c3: '#442266' },
    steel:    { c1: '#aaaacc', c2: '#ccccee', c3: '#8888aa' },
    normal:   { c1: '#aaaa88', c2: '#ccccaa', c3: '#888866' }
};
```

---

## 12. God Rays / Volumetric Light

### 12.1 Concept

God rays (crepuscular rays) create dramatic beams of light radiating from a bright source. Perfect for:
- Victory/KO moments
- Legendary pokemon entrance
- Ultimate attack charging

### 12.2 God Ray Post-Process Shader

```glsl
// god_rays.frag — Screen-space volumetric light scattering
precision highp float;

uniform sampler2D tDiffuse;
uniform vec2 uLightPosition;  // light source in screen space (0-1)
uniform float uExposure;      // 0.3
uniform float uDecay;         // 0.95
uniform float uDensity;       // 0.8
uniform float uWeight;        // 0.4
uniform int uSamples;         // 60

varying vec2 vUv;

void main() {
    vec2 deltaTextCoord = vUv - uLightPosition;
    deltaTextCoord *= 1.0 / float(uSamples) * uDensity;

    vec2 coord = vUv;
    vec4 color = texture2D(tDiffuse, coord);

    float illuminationDecay = 1.0;

    for (int i = 0; i < 60; i++) {
        if (i >= uSamples) break;
        coord -= deltaTextCoord;
        vec4 sampleColor = texture2D(tDiffuse, coord);
        sampleColor *= illuminationDecay * uWeight;
        color += sampleColor;
        illuminationDecay *= uDecay;
    }

    gl_FragColor = color * uExposure;
}
```

### 12.3 Three.js Integration

```javascript
const GodRayShader = {
    uniforms: {
        tDiffuse:       { value: null },
        uLightPosition: { value: new THREE.Vector2(0.5, 0.5) },
        uExposure:      { value: 0.3 },
        uDecay:         { value: 0.95 },
        uDensity:       { value: 0.8 },
        uWeight:        { value: 0.4 },
        uSamples:       { value: 60 }
    },
    vertexShader: `
        varying vec2 vUv;
        void main() {
            vUv = uv;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
    `,
    fragmentShader: godRaysFrag
};

// Convert 3D position to screen coordinates for the light source
function worldToScreen(position, camera) {
    const vec = position.clone().project(camera);
    return new THREE.Vector2(
        (vec.x + 1) / 2,
        (vec.y + 1) / 2
    );
}
```

---

## 13. Performance Optimization

### 13.1 Mobile-Friendly Shader Tips

```glsl
// Use mediump where possible on mobile
#ifdef GL_ES
precision mediump float;
#endif

// Reduce FBM octaves on mobile
#ifdef MOBILE
#define NUM_OCTAVES 3
#else
#define NUM_OCTAVES 6
#endif
```

### 13.2 Resolution Scaling

```javascript
// Render effects at half resolution for performance
function createHalfResRenderTarget(renderer) {
    const size = renderer.getSize(new THREE.Vector2());
    return new THREE.WebGLRenderTarget(
        Math.floor(size.x / 2),
        Math.floor(size.y / 2),
        { minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter }
    );
}
```

### 13.3 Object Pooling for Particles

```javascript
class ParticlePool {
    constructor(maxCount) {
        this.pool = [];
        this.active = [];
        this.maxCount = maxCount;
    }

    acquire() {
        if (this.pool.length > 0) {
            const p = this.pool.pop();
            this.active.push(p);
            return p;
        }
        if (this.active.length < this.maxCount) {
            const p = { position: new THREE.Vector3(), velocity: new THREE.Vector3(), life: 0 };
            this.active.push(p);
            return p;
        }
        return null; // pool exhausted
    }

    release(particle) {
        const idx = this.active.indexOf(particle);
        if (idx !== -1) {
            this.active.splice(idx, 1);
            this.pool.push(particle);
        }
    }

    update(dt) {
        for (let i = this.active.length - 1; i >= 0; i--) {
            const p = this.active[i];
            p.life -= dt;
            if (p.life <= 0) {
                this.release(p);
            }
        }
    }
}
```

### 13.4 LOD for Effects

```javascript
// Reduce effect quality based on FPS
class AdaptiveQuality {
    constructor() {
        this.fps = 60;
        this.frameCount = 0;
        this.lastTime = performance.now();
        this.quality = 1.0; // 0.0 = minimum, 1.0 = maximum
    }

    update() {
        this.frameCount++;
        const now = performance.now();
        if (now - this.lastTime >= 1000) {
            this.fps = this.frameCount;
            this.frameCount = 0;
            this.lastTime = now;

            // Adjust quality
            if (this.fps < 30) this.quality = Math.max(0.3, this.quality - 0.1);
            else if (this.fps > 55) this.quality = Math.min(1.0, this.quality + 0.05);
        }
    }

    getParticleCount(base) { return Math.floor(base * this.quality); }
    getOctaves() { return this.quality > 0.7 ? 6 : this.quality > 0.4 ? 4 : 2; }
    getBloomSamples() { return this.quality > 0.5 ? 5 : 3; }
}
```

### 13.5 Disposing Resources

```javascript
function disposeEffect(mesh) {
    if (mesh.geometry) mesh.geometry.dispose();
    if (mesh.material) {
        if (mesh.material.map) mesh.material.map.dispose();
        mesh.material.dispose();
    }
    if (mesh.parent) mesh.parent.remove(mesh);
}
```

---

## Quick Reference: Effect Pipeline per Attack Type

| Type | Shader Effect | Particles | Post-Process | Sound |
|------|--------------|-----------|--------------|-------|
| Fire | fire_vortex.frag | fire sparks (orange/yellow) | bloom(1.2), radial blur | fire_whoosh + fire_explosion |
| Water | wave distortion | water droplets (blue/white) | bloom(0.5) | splash + impact |
| Electric | lightning.frag | electric sparks (yellow/white) | bloom(1.5), chromatic aberration | electric_zap + thunder |
| Ice | crystal formation | ice shards (cyan/white) | bloom(0.6), white flash | ice_freeze + shatter |
| Psychic | psychic_wave.frag + energy_field.frag | energy wisps (purple/pink) | chromatic aberration, distortion wave | psychic_hum + psychic_wave |
| Dark | dark vignette | shadow particles (purple/black) | bloom(0.3), screen darken | dark_pulse + ominous |
| Dragon | fire_vortex (blue) + lightning | dragon flames (blue/purple) | bloom(1.0), screen shake | fire_beam + thunder |
| Fairy | sparkle field | glitter (pink/white) | bloom(0.7), soft glow | fairy_sparkle + chime |
| Fighting | impact ring | debris (brown/gray) | radial blur, screen shake | punch + impact_heavy |
| Ghost | dissolve shader | phantom wisps (purple) | distortion, desaturation | ghost_whisper + dark |
| Poison | bubble/drip shader | toxic bubbles (purple/green) | color shift to purple | bubble + hiss |
| Ground | crack propagation | rocks/debris (brown) | screen shake (strong) | rumble + impact |
| Flying | wind lines | feathers/wind (white/blue) | motion blur | whoosh + wind |
| Steel | metallic flash | metal sparks (silver) | bloom(0.8), white flash | clang + metallic |

---

## Resource Links Summary

### Libraries
- **Three.js r170+**: `https://threejs.org/` — Core 3D engine
- **Howler.js 2.2.x**: `https://howlerjs.com/` — Audio engine
- **audiosprite**: `npm install -g audiosprite` — Audio sprite generator

### Shader References
- **GLSL noise functions**: `https://gist.github.com/patriciogonzalezvivo/670c22f3966e662d2f83`
- **Lygia shader library**: `https://lygia.xyz/generative`
- **Shadertoy**: `https://www.shadertoy.com/` — Shader playground
- **The Book of Shaders**: `https://thebookofshaders.com/` — GLSL tutorial
- **Inigo Quilez articles**: `https://iquilezles.org/articles/` — Advanced SDF and noise

### Free Sound Effects
- **Mixkit**: `https://mixkit.co/free-sound-effects/` — Free, no attribution required
- **Freesound.org**: `https://freesound.org/` — CC0/CC-BY sounds (check license per file)
- **Pixabay**: `https://pixabay.com/sound-effects/` — Free, no attribution required

### Three.js Shaders (built-in)
- **RGBShiftShader** (chromatic aberration): `three/examples/jsm/shaders/RGBShiftShader.js`
- **LuminosityHighPassShader** (bloom): `three/examples/jsm/shaders/LuminosityHighPassShader.js`
- **UnrealBloomPass**: `three/examples/jsm/postprocessing/UnrealBloomPass.js`
- **EffectComposer**: `three/examples/jsm/postprocessing/EffectComposer.js`
- **ShaderPass**: `three/examples/jsm/postprocessing/ShaderPass.js`
- **RenderPass**: `three/examples/jsm/postprocessing/RenderPass.js`
