# Pokemon 3D Battle Visualization - Research Notes

> Telegram Mini App (single HTML file, Three.js + Web Audio API)

---

## 1. Sound Effects - Free Sources & Libraries

### Free SFX Platforms (No Attribution Required)

| Platform | URL | License | Format |
|----------|-----|---------|--------|
| **Pixabay** | https://pixabay.com/sound-effects/ | Royalty-free, no attribution | MP3 |
| **Mixkit** | https://mixkit.co/free-sound-effects/ | Royalty-free, no attribution | WAV/MP3 |
| **Freesound.org** | https://freesound.org/ | CC0/CC-BY (varies per sound) | WAV/OGG/MP3 |
| **OpenGameArt** | https://opengameart.org/ | CC0/CC-BY (varies) | Various |
| **Zapsplat** | https://www.zapsplat.com/ | Free with attribution | WAV/MP3 |

### Specific Search URLs for Needed Sounds

| Sound | Pixabay URL | Mixkit URL |
|-------|-------------|------------|
| Battle Hit/Impact | https://pixabay.com/sound-effects/search/impact/ | https://mixkit.co/free-sound-effects/impact/ |
| Fire Whoosh | https://pixabay.com/sound-effects/search/fire%20whoosh/ | https://mixkit.co/free-sound-effects/whoosh/ |
| Ice/Crystal | https://pixabay.com/sound-effects/search/ice/ | https://mixkit.co/free-sound-effects/ice/ |
| Electric Zap | https://pixabay.com/sound-effects/search/electric/ | https://mixkit.co/free-sound-effects/electric/ |
| Beam Charge | https://pixabay.com/sound-effects/search/beam/ | https://mixkit.co/free-sound-effects/laser/ |
| Crowd Cheer | https://pixabay.com/sound-effects/search/crowd/ | https://mixkit.co/free-sound-effects/cheer/ |
| Victory | https://pixabay.com/sound-effects/search/victory/ | https://mixkit.co/free-sound-effects/win/ |
| Game Effects | https://pixabay.com/sound-effects/search/game/ | https://mixkit.co/free-sound-effects/game/ |

### Freesound.org Specific Sounds Found

- **Electric zap**: https://freesound.org/people/michael_grinnell/sounds/512471/ (electric_zap.wav)
- **Electrical Shock**: https://freesound.org/people/BigKahuna360/sounds/160421/
- **Whoosh pack**: https://freesound.org/people/Robinhood76/packs/6417/ (Swoosh WHOOSH air effects)
- **Impact hits**: https://freesound.org/people/waveplaySFX/packs/12552/ (EDM impacts pack)

### Howler.js - Recommended Audio Library

- **Size**: ~7KB gzipped, zero dependencies
- **CDN**: `<script src="https://cdnjs.cloudflare.com/ajax/libs/howler/2.2.4/howler.min.js"></script>`
- **Spatial audio plugin**: Built-in 3D positional audio
- **Format priority**: Use `webm` first, `mp3` fallback (best compression + quality)
- **Docs**: https://howlerjs.com/
- **GitHub**: https://github.com/goldfire/howler.js/

```javascript
// Basic Howler.js usage for battle SFX
const hitSound = new Howl({
  src: ['hit.webm', 'hit.mp3'],
  volume: 0.8,
  sprite: {  // Audio sprite - multiple sounds in one file
    light_hit: [0, 300],
    heavy_hit: [400, 600],
    critical: [1100, 800]
  }
});
hitSound.play('heavy_hit');
```

### Web Audio API Best Practices (MDN)

1. **Autoplay Policy**: AudioContext must be created/resumed from user gesture (click/tap)
   - Telegram Mini App: Resume context on first user interaction
   - `audioContext.resume()` after user tap
2. **Audio Sprites**: Combine multiple short SFX into one file, use start/stop times
   - Reduces HTTP requests, better for mobile
3. **Mobile priming trick**: Include silence at end of audio, play+pause it on first touch
4. **Format**: WebM > MP3 for quality/size ratio
5. **Reference**: https://developer.mozilla.org/en-US/docs/Games/Techniques/Audio_for_Web_Games

---

## 2. Pokemon Battle UI Reference

### Pokemon Sword/Shield Battle UI

- **Source**: https://www.gameuidatabase.com/gameData.php?id=30 (55,000+ UI screenshots)
- **Layout**:
  - Player's Pokemon info: **bottom-left** of screen
  - Opponent's Pokemon info: **top-right** of screen
  - Move menu: **bottom-right** (Fight / Pokemon / Bag / Run)
- **HP Bar Design**:
  - White card/panel background, minimal style
  - HP bar: thin horizontal bar
  - Green (#8DC115 / rgb(141,193,21)) when >50% HP
  - Yellow when 20-50% HP
  - Red when <20% HP (alarm sound plays ~3 sec)
  - XP bar: thin bar below HP bar
  - Pokemon name + Level displayed
  - Gender icon shown
- **Style**: Extremely minimalistic, clean white panels, high contrast

### Pokemon Scarlet/Violet Battle UI

- **Source**: https://www.gameuidatabase.com/gameData.php?id=1579
- **UI Redesign study**: https://www.behance.net/gallery/153919867/GAME-UI-REDESIGN-POKEMON-SCARLETVIOLET
- Similar layout to Sword/Shield but with updated visual style

### HP Bar Color Thresholds (All Pokemon Games)

```
HP > 50%  → Green  (#4CAF50 or #8DC115)
HP 20-50% → Yellow (#FFC107 or #F5C742)
HP < 20%  → Red    (#F44336 or #E53935)
```

### Recommended CSS for HP Bar

```css
.hp-bar {
  height: 8px;
  border-radius: 4px;
  background: linear-gradient(90deg, #4CAF50, #6BC84F);
  transition: width 0.8s ease-out, background-color 0.5s;
}
.hp-bar.yellow { background: linear-gradient(90deg, #F5C742, #FFC107); }
.hp-bar.red { background: linear-gradient(90deg, #E53935, #F44336); }
```

---

## 3. Three.js Advanced Effects

### Particle Systems

#### Approach 1: BufferGeometry + ShaderMaterial (Best Performance)

```javascript
// GPU particles via custom shader
const geometry = new THREE.BufferGeometry();
const positions = new Float32Array(PARTICLE_COUNT * 3);
const velocities = new Float32Array(PARTICLE_COUNT * 3);

geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
geometry.setAttribute('velocity', new THREE.BufferAttribute(velocities, 3));

const material = new THREE.ShaderMaterial({
  vertexShader: `
    attribute vec3 velocity;
    uniform float uTime;
    varying float vLife;
    void main() {
      vec3 pos = position + velocity * uTime;
      vLife = 1.0 - length(pos) / 5.0;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
      gl_PointSize = vLife * 10.0;
    }
  `,
  fragmentShader: `
    varying float vLife;
    uniform vec3 uColor;
    void main() {
      float d = length(gl_PointCoord - 0.5);
      if (d > 0.5) discard;
      gl_FragColor = vec4(uColor, vLife * (1.0 - d * 2.0));
    }
  `,
  transparent: true, blending: THREE.AdditiveBlending, depthWrite: false
});
```

#### Approach 2: ShaderParticleEngine Library

- **GitHub**: https://github.com/squarefeet/ShaderParticleEngine
- GPU-driven, supports emitters with position, velocity, acceleration, color over lifetime
- Good for fire/smoke/sparks

#### Approach 3: SmokeGL (Fire + Smoke specific)

- **GitHub**: https://github.com/SqrtPapere/SmokeGL
- Discards fragments outside circles for spherical particles
- Handles texture rotation and transparency sorting

### Effect-Specific Techniques

#### Fire Effect
- Particles rise with turbulence (Perlin noise in shader)
- Color gradient: white core → yellow → orange → red → transparent
- Additive blending, billboard sprites
- Point size decreases as particle ages

#### Ice/Crystal Effect
- Geometry-based: small IcosahedronGeometry shards
- MeshPhysicalMaterial with transmission/ior for glass-like look
- Particles expand outward, slight gravity, slow spin
- Color: white → cyan → blue, some opacity

#### Electric Effect
- Line segments between random points (THREE.Line)
- Regenerate positions each frame for "crackling" look
- Branching: recursive subdivision of line segments
- Color: bright yellow/white core, blue/purple glow
- Bloom post-processing enhances this greatly

#### Psychic Effect
- Concentric expanding rings (TorusGeometry or shader)
- Distortion shader on background (heat haze technique)
- Color: pink → purple, swirling motion
- Noise-based vertex displacement

### Post-Processing (pmndrs/postprocessing)

- **GitHub**: https://github.com/pmndrs/postprocessing
- **CDN**: Available via unpkg/skypack

Key effects for battle visualization:
1. **Bloom/UnrealBloom**: Glow on energy attacks, fire, electric
2. **ChromaticAberration**: On heavy impacts, screen shake moments
3. **Motion Blur**: During fast attacks (velocity buffer based)
4. **Screen Shake**: Camera displacement + rotation on impacts
5. **Vignette**: Dramatic framing during special moves

```javascript
import { EffectComposer, RenderPass, BloomEffect, EffectPass }
  from 'https://cdn.skypack.dev/postprocessing';

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
composer.addPass(new EffectPass(camera, new BloomEffect({
  intensity: 1.5, luminanceThreshold: 0.6
})));
```

### Heat Haze / Distortion Shader

- **Tutorial**: https://tympanus.net/codrops/2016/05/03/animated-heat-distortion-effects-webgl/
- Technique: Render scene to texture, apply UV distortion in post-pass
- Use noise texture scrolling to offset UV coordinates
- Great for fire/psychic background effects

---

## 4. Pokeball Throw Animation

### 3D Models Available

- **Sketchfab (animated)**: https://sketchfab.com/3d-models/pokeball-animated-73634eaf5c7543428ab7359864087383
- **Sketchfab (opening)**: https://sketchfab.com/3d-models/pokeball-animation-pokeball-opening-7946753d7444443cafb04725f96ec86c
- **Three.js Pokeball**: https://github.com/prafulla-codes/three-pokeball
- **CodePen 3D Pokeball**: https://codepen.io/Sukk4/pen/VjNowW

### Throw Arc Animation (Parabolic Trajectory)

```javascript
function animatePokeball(ball, startPos, targetPos, duration) {
  const arcHeight = 3.0;  // peak height of arc
  let elapsed = 0;

  function update(dt) {
    elapsed += dt;
    const t = Math.min(elapsed / duration, 1.0);

    // Horizontal: linear interpolation
    ball.position.x = THREE.MathUtils.lerp(startPos.x, targetPos.x, t);
    ball.position.z = THREE.MathUtils.lerp(startPos.z, targetPos.z, t);

    // Vertical: parabolic arc  y = -4h*t^2 + 4h*t + startY
    ball.position.y = startPos.y + arcHeight * 4 * t * (1 - t);

    // Spin during flight
    ball.rotation.x += dt * 10;
    ball.rotation.z += dt * 5;

    return t >= 1.0; // done
  }
  return update;
}
```

### Pokeball Open / Release Effect

Sequence:
1. Ball hits target position, brief pause
2. Ball splits open (top half rotates up ~120deg)
3. White flash (PointLight intensity spike + white sphere scale up)
4. Energy particles burst outward (spherical emission)
5. Pokemon materializes (scale from 0 + opacity fade in)
6. Sparkle particles settle around Pokemon

```javascript
// Flash effect on open
const flashLight = new THREE.PointLight(0xffffff, 0, 10);
flashLight.position.copy(ball.position);
scene.add(flashLight);

// Animate: intensity 0 → 5 → 0 over 0.5s
gsap.to(flashLight, { intensity: 5, duration: 0.15 })
    .then(() => gsap.to(flashLight, { intensity: 0, duration: 0.35 }));
```

### Creating Pokeball in Three.js (No External Model)

```javascript
function createPokeball() {
  const group = new THREE.Group();
  const radius = 0.3;

  // Top half (red)
  const topGeo = new THREE.SphereGeometry(radius, 32, 16, 0, Math.PI*2, 0, Math.PI/2);
  const topMat = new THREE.MeshStandardMaterial({ color: 0xEE1515 });
  group.add(new THREE.Mesh(topGeo, topMat));

  // Bottom half (white)
  const botGeo = new THREE.SphereGeometry(radius, 32, 16, 0, Math.PI*2, Math.PI/2, Math.PI/2);
  const botMat = new THREE.MeshStandardMaterial({ color: 0xFFFFFF });
  group.add(new THREE.Mesh(botGeo, botMat));

  // Center band (black)
  const bandGeo = new THREE.TorusGeometry(radius, 0.02, 8, 32);
  const bandMat = new THREE.MeshStandardMaterial({ color: 0x222222 });
  const band = new THREE.Mesh(bandGeo, bandMat);
  band.rotation.x = Math.PI / 2;
  group.add(band);

  // Center button (white circle with black ring)
  const btnGeo = new THREE.CircleGeometry(0.06, 16);
  const btnMat = new THREE.MeshStandardMaterial({ color: 0xFFFFFF });
  const btn = new THREE.Mesh(btnGeo, btnMat);
  btn.position.z = radius;
  group.add(btn);

  return group;
}
```

---

## 5. Trainer Representation

### Free 3D Models

| Source | URL | Notes |
|--------|-----|-------|
| Sketchfab | https://sketchfab.com/3d-models/pokemon-trainer-9792003f622b4b41bb25df9dff2aad89 | Free download |
| CGTrader | https://www.cgtrader.com/free-3d-models/pokemon | 59+ free models |
| Free3D | https://free3d.com/3d-models/pokemon | 532 free models |
| Poly Pizza | https://poly.pizza/ | Low poly, no login needed |
| TurboSquid | https://www.turbosquid.com/Search/3D-Models/free/pokemon-character | Free section |

### Simple Trainer Representation (No External Models)

For a single HTML file approach, creating trainers procedurally is better than loading glTF:

1. **Silhouette approach**: Dark 2D plane with trainer shape cutout, backlit
2. **Simple mesh**: Capsule body + sphere head + cylinder arms
3. **Billboard sprite**: 2D image on a plane that faces camera

```javascript
// Simple trainer silhouette
function createTrainer(isPlayer) {
  const group = new THREE.Group();

  // Body (capsule)
  const bodyGeo = new THREE.CapsuleGeometry(0.3, 0.8, 4, 8);
  const bodyMat = new THREE.MeshStandardMaterial({
    color: isPlayer ? 0x2196F3 : 0xF44336,
    roughness: 0.7
  });
  group.add(new THREE.Mesh(bodyGeo, bodyMat));

  // Head
  const headGeo = new THREE.SphereGeometry(0.2, 16, 16);
  const head = new THREE.Mesh(headGeo, bodyMat);
  head.position.y = 0.7;
  group.add(head);

  return group;
}
```

### Battle Positioning (Pokemon Game Convention)

- **Player's Pokemon**: Bottom-left, facing away from camera (back visible)
- **Opponent's Pokemon**: Top-right, facing toward camera (front visible)
- **Player trainer**: Far bottom-left, behind player's Pokemon (often not visible during moves)
- **Opponent trainer**: Far top-right, behind opponent's Pokemon
- **Camera angle**: Slightly elevated, looking down at ~20-30 degree angle
- **During attacks**: Camera dynamically moves to show attacker → defender

---

## 6. Spectator / Crowd Effects

### Pokemon Game References

| Game | Crowd Style |
|------|-------------|
| Pokemon Stadium (N64) | Flat 2D spectators in stadium seats, simple color animation |
| Pokemon Colosseum (GCN) | 3D stadium with billboard crowd sprites |
| Pokemon Battle Revolution (Wii) | Most detailed - animated 3D crowd, cheering/waving |
| Pokemon Sword/Shield | Stadium battles (Gym/Champion) have crowd in stands |

### Three.js Crowd Implementation

#### InstancedMesh Billboard Approach (Best for Performance)

```javascript
// Create crowd using InstancedMesh + billboard shader
const crowdCount = 500;
const planeGeo = new THREE.PlaneGeometry(0.3, 0.5);
const crowdMat = new THREE.ShaderMaterial({
  vertexShader: `
    // Billboard: always face camera
    void main() {
      vec4 mvPosition = modelViewMatrix * instanceMatrix * vec4(0,0,0,1);
      mvPosition.xy += position.xy * vec2(0.3, 0.5);
      gl_Position = projectionMatrix * mvPosition;
    }
  `,
  fragmentShader: `
    uniform vec3 uColors[5];
    void main() {
      gl_FragColor = vec4(uColors[int(mod(gl_FragCoord.x, 5.0))], 1.0);
    }
  `
});

const crowd = new THREE.InstancedMesh(planeGeo, crowdMat, crowdCount);
const dummy = new THREE.Object3D();

for (let i = 0; i < crowdCount; i++) {
  const angle = (i / crowdCount) * Math.PI * 2;
  const radius = 15 + Math.random() * 5;
  dummy.position.set(
    Math.cos(angle) * radius,
    2 + Math.random() * 3,  // varying heights in stands
    Math.sin(angle) * radius
  );
  dummy.updateMatrix();
  crowd.setMatrixAt(i, dummy.matrix);
  crowd.setColorAt(i, new THREE.Color().setHSL(Math.random(), 0.5, 0.6));
}
```

#### InstancedSpriteMesh (Best Library)

- **Docs**: https://three-kit.vercel.app/instancedsprite/01-instanced-sprite-mesh/
- Tens of thousands of individually animated sprites
- Works on low/medium power devices
- Single draw call for entire crowd

#### Crowd Reactions

```javascript
// Animate crowd bounce on exciting moments
function crowdReaction(crowd, intensity) {
  const time = performance.now() * 0.003;
  const dummy = new THREE.Object3D();

  for (let i = 0; i < crowd.count; i++) {
    crowd.getMatrixAt(i, dummy.matrix);
    dummy.matrix.decompose(dummy.position, dummy.quaternion, dummy.scale);

    // Bounce with phase offset per spectator
    const phase = i * 0.5;
    dummy.position.y += Math.sin(time + phase) * 0.1 * intensity;

    dummy.updateMatrix();
    crowd.setMatrixAt(i, dummy.matrix);
  }
  crowd.instanceMatrix.needsUpdate = true;
}
```

---

## 7. Telegram Mini App Considerations

### Performance Constraints

- Runs in **WebView** (not full browser) - reduced GPU/CPU budget
- Lower-end Android devices struggle with complex WebGL
- Recommendation: Implement quality settings (Low/Medium/High)
- Consider disabling post-processing on low-end devices
- Keep triangle count under 50K for smooth performance

### Single HTML File Setup

```html
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
</head>
<body style="margin:0; overflow:hidden;">
<script type="importmap">
{
  "imports": {
    "three": "https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js",
    "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/"
  }
}
</script>
<script type="module">
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';

// Howler for audio (non-module)
// <script src="https://cdnjs.cloudflare.com/ajax/libs/howler/2.2.4/howler.min.js">

const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();

// ... battle scene code
</script>
</body>
</html>
```

### Audio in Telegram Mini App

- AudioContext requires user gesture - use Telegram WebApp button or first touch
- Preload sounds during loading screen
- Use audio sprites (single file, multiple sounds) to reduce network requests
- Fallback: Vibration API for impact feedback (`navigator.vibrate(50)`)

---

## 8. Practical Architecture for Single HTML File

### Recommended Stack

| Component | Library | CDN |
|-----------|---------|-----|
| 3D Rendering | Three.js r170+ | jsdelivr.net |
| Post-processing | Three.js addons | jsdelivr.net |
| Audio | Howler.js 2.2.x | cdnjs.cloudflare.com |
| Animation | Built-in (requestAnimationFrame) | N/A |
| Tweening | gsap or manual | cdnjs (optional) |

### Scene Structure

```
Scene
├── Stadium
│   ├── Floor (CircleGeometry with grass texture)
│   ├── Arena boundary (ring/cylinder)
│   └── Stands (tiered geometry for crowd)
├── Crowd (InstancedMesh, 200-500 instances)
├── Player Side
│   ├── Trainer (simple mesh or billboard)
│   └── Pokemon (billboard sprite + animations)
├── Opponent Side
│   ├── Trainer
│   └── Pokemon
├── Effects Layer
│   ├── Particle systems (per-attack type)
│   ├── Pokeball (throwable)
│   └── Impact flashes
├── UI (HTML overlay, not 3D)
│   ├── Player HP bar (bottom-left)
│   ├── Opponent HP bar (top-right)
│   ├── Move selection (bottom)
│   └── Battle log
├── Lights
│   ├── Ambient (soft fill)
│   ├── Directional (main sun/stadium light)
│   └── Point lights (dynamic, for effects)
└── Camera (PerspectiveCamera, animated between positions)
```

### Performance Budget (Telegram Mini App Target)

| Metric | Target |
|--------|--------|
| Total triangles | <50,000 |
| Draw calls | <30 (use InstancedMesh) |
| Texture memory | <32MB |
| Particle count | <2,000 active |
| Target FPS | 30+ (mobile), 60 (desktop) |
| Initial load | <2MB total |

---

## Key Reference Links Summary

### Tutorials & Guides
- [Three.js Particles](https://threejs-journey.com/lessons/particles)
- [GPGPU Particles (Codrops)](https://tympanus.net/codrops/2024/12/19/crafting-a-dreamy-particle-effect-with-three-js-and-gpgpu/)
- [Heat Distortion WebGL (Codrops)](https://tympanus.net/codrops/2016/05/03/animated-heat-distortion-effects-webgl/)
- [Dissolve Effect (Codrops)](https://tympanus.net/codrops/2025/02/17/implementing-a-dissolve-effect-with-shaders-and-particles-in-three-js/)
- [Web Audio for Games (MDN)](https://developer.mozilla.org/en-US/docs/Games/Techniques/Audio_for_Web_Games)
- [Three.js Billboards](https://threejs.org/manual/en/billboards.html)
- [Sprite Animations (SpriteMixer)](https://github.com/felixmariotto/three-SpriteMixer)
- [Three.js CDN Setup](https://cdnjs.com/libraries/three.js/)

### UI References
- [Pokemon Sword/Shield UI (Game UI Database)](https://www.gameuidatabase.com/gameData.php?id=30)
- [Pokemon Scarlet/Violet UI (Game UI Database)](https://www.gameuidatabase.com/gameData.php?id=1579)
- [Sword/Shield UI Redesign (ArtStation)](https://www.artstation.com/artwork/A9DZLq)
- [HP Bar Colors (Bulbapedia)](https://bulbapedia.bulbagarden.net/wiki/HP)

### Audio
- [Howler.js](https://howlerjs.com/)
- [Web Audio API Best Practices (MDN)](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API/Best_practices)

### Post-Processing
- [pmndrs/postprocessing](https://github.com/pmndrs/postprocessing)
- [Three.js Journey Post-processing](https://threejs-journey.com/lessons/post-processing)

### Crowd / Instancing
- [InstancedSpriteMesh](https://three-kit.vercel.app/instancedsprite/01-instanced-sprite-mesh/)
- [One Draw Call Massive Crowd (Forum)](https://discourse.threejs.org/t/one-draw-call-massive-crowd-performance-engineering-in-three-js/89928)

### 3D Models
- [Three.js Pokeball (GitHub)](https://github.com/prafulla-codes/three-pokeball)
- [Pokeball Animated (Sketchfab)](https://sketchfab.com/3d-models/pokeball-animated-73634eaf5c7543428ab7359864087383)
- [Pokemon Trainer (Sketchfab)](https://sketchfab.com/3d-models/pokemon-trainer-9792003f622b4b41bb25df9dff2aad89)
- [Poly Pizza (Free Low Poly)](https://poly.pizza/)

### Telegram
- [Telegram Mini Apps Docs](https://core.telegram.org/bots/webapps)
