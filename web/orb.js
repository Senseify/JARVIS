/**
 * JARVIS OS — Three.js Procedural Spatial Orb Subsystem
 *
 * Procedural energy sphere driven by custom GLSL 3D Simplex noise shaders,
 * mechanical counter-rotating gimbal rings, bracket markers, particle field,
 * mouse parallax, and real-time state reactivity.
 */

(function () {
  'use strict';

  // Simplex 3D Noise GLSL Implementation
  const simplexNoiseGLSL = `
    vec4 permute(vec4 x){return mod(((x*34.0)+1.0)*x, 289.0);}
    vec4 taylorInvSqrt(vec4 r){return 1.79284291400159 - 0.85373472095314 * r;}

    float snoise(vec3 v){
      const vec2  C = vec2(1.0/6.0, 1.0/3.0);
      const vec4  D = vec4(0.0, 0.5, 1.0, 2.0);

      vec3 i  = floor(v + dot(v, C.yyy) );
      vec3 x0 = v - i + dot(i, C.xxx) ;

      vec3 g = step(x0.yzx, x0.xyz);
      vec3 l = 1.0 - g;
      vec3 i1 = min( g.xyz, l.zxy );
      vec3 i2 = max( g.xyz, l.zxy );

      vec3 x1 = x0 - i1 + 1.0 * C.xxx;
      vec3 x2 = x0 - i2 + 2.0 * C.xxx;
      vec3 x3 = x0 - 1.0 + 3.0 * C.xxx;

      i = mod(i, 289.0 );
      vec4 p = permute( permute( permute(
                 i.z + vec4(0.0, i1.z, i2.z, 1.0 ))
               + i.y + vec4(0.0, i1.y, i2.y, 1.0 ))
               + i.x + vec4(0.0, i1.x, i2.x, 1.0 ));

      float n_ = 0.142857142857;
      vec3  ns = n_ * D.wyz - D.xzx;

      vec4 j = p - 49.0 * floor(p * ns.z *ns.z);

      vec4 x_ = floor(j * ns.z);
      vec4 y_ = floor(j - 7.0 * x_ );

      vec4 x = x_ *ns.x + ns.yyyy;
      vec4 y = y_ *ns.x + ns.yyyy;
      vec4 h = 1.0 - abs(x) - abs(y);

      vec4 b0 = vec4( x.xy, y.xy );
      vec4 b1 = vec4( x.zw, y.zw );

      vec4 s0 = floor(b0)*2.0 + 1.0;
      vec4 s1 = floor(b1)*2.0 + 1.0;
      vec4 sh = -step(h, vec4(0.0));

      vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy ;
      vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww ;

      vec3 p0 = vec3(a0.xy,h.x);
      vec3 p1 = vec3(a0.zw,h.y);
      vec3 p2 = vec3(a1.xy,h.z);
      vec3 p3 = vec3(a1.zw,h.w);

      vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2, p2), dot(p3,p3)));
      p0 *= norm.x;
      p1 *= norm.y;
      p2 *= norm.z;
      p3 *= norm.w;

      vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
      m = m * m;
      return 42.0 * dot( m*m, vec4( dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3) ) );
    }
  `;

  // Vertex Shader
  const vertexShader = `
    ${simplexNoiseGLSL}

    uniform float uTime;
    uniform float uDisplacement;
    uniform float uNoiseScale;
    uniform float uNoiseSpeed;

    varying vec3 vNormal;
    varying vec3 vPosition;
    varying float vNoise;

    void main() {
      vNormal = normalize(normalMatrix * normal);
      vPosition = position;

      float noise = snoise(position * uNoiseScale + vec3(0.0, 0.0, uTime * uNoiseSpeed));
      vNoise = noise;

      vec3 newPosition = position + normal * (noise * uDisplacement);
      gl_Position = projectionMatrix * modelViewMatrix * vec4(newPosition, 1.0);
    }
  `;

  // Fragment Shader
  const fragmentShader = `
    uniform vec3 uCoreColor;
    uniform vec3 uRimColor;
    uniform float uFresnelPower;
    uniform float uIntensity;
    uniform float uTime;

    varying vec3 vNormal;
    varying vec3 vPosition;
    varying float vNoise;

    void main() {
      vec3 viewDir = normalize(-vPosition);
      float fresnel = pow(1.0 - max(dot(vNormal, viewDir), 0.0), uFresnelPower);

      // Core glow modulated by procedural noise
      vec3 color = mix(uCoreColor, uRimColor, fresnel + (vNoise * 0.15));
      color *= (uIntensity + sin(uTime * 2.0) * 0.08);

      gl_FragColor = vec4(color, 0.88 + fresnel * 0.12);
    }
  `;

  // Predefined Orb States
  const ORB_CONFIGS = {
    IDLE: {
      coreColor: [0.02, 0.45, 0.85],
      rimColor: [0.35, 0.88, 1.0],
      displacement: 0.16,
      noiseSpeed: 0.6,
      noiseScale: 0.9,
      fresnelPower: 2.2,
      intensity: 1.0,
      gimbalSpeed: 0.008,
    },
    OBSERVE: {
      coreColor: [0.1, 0.6, 0.95],
      rimColor: [0.95, 0.8, 0.2],
      displacement: 0.26,
      noiseSpeed: 1.2,
      noiseScale: 1.2,
      fresnelPower: 1.8,
      intensity: 1.2,
      gimbalSpeed: 0.015,
    },
    LISTENING: {
      coreColor: [0.05, 0.65, 0.95],
      rimColor: [0.4, 0.95, 1.0],
      displacement: 0.32,
      noiseSpeed: 1.5,
      noiseScale: 1.4,
      fresnelPower: 1.6,
      intensity: 1.3,
      gimbalSpeed: 0.02,
    },
    UNDERSTAND: {
      coreColor: [0.35, 0.18, 0.85],
      rimColor: [0.75, 0.5, 1.0],
      displacement: 0.34,
      noiseSpeed: 1.8,
      noiseScale: 1.5,
      fresnelPower: 2.0,
      intensity: 1.25,
      gimbalSpeed: 0.022,
    },
    PLAN: {
      coreColor: [0.85, 0.55, 0.05],
      rimColor: [0.4, 0.9, 1.0],
      displacement: 0.28,
      noiseSpeed: 1.4,
      noiseScale: 1.8,
      fresnelPower: 1.9,
      intensity: 1.2,
      gimbalSpeed: 0.018,
    },
    ACT: {
      coreColor: [0.02, 0.8, 0.85],
      rimColor: [1.0, 1.0, 1.0],
      displacement: 0.48,
      noiseSpeed: 2.8,
      noiseScale: 2.0,
      fresnelPower: 1.4,
      intensity: 1.45,
      gimbalSpeed: 0.045,
    },
    VERIFY: {
      coreColor: [0.05, 0.75, 0.45],
      rimColor: [0.4, 1.0, 0.75],
      displacement: 0.22,
      noiseSpeed: 1.3,
      noiseScale: 1.1,
      fresnelPower: 2.1,
      intensity: 1.15,
      gimbalSpeed: 0.012,
    },
    RECOVER: {
      coreColor: [0.95, 0.4, 0.05],
      rimColor: [1.0, 0.2, 0.2],
      displacement: 0.42,
      noiseSpeed: 2.2,
      noiseScale: 1.6,
      fresnelPower: 1.7,
      intensity: 1.35,
      gimbalSpeed: 0.03,
    },
    REMEMBER: {
      coreColor: [0.5, 0.15, 0.9],
      rimColor: [0.85, 0.6, 1.0],
      displacement: 0.2,
      noiseSpeed: 0.9,
      noiseScale: 1.3,
      fresnelPower: 2.3,
      intensity: 1.1,
      gimbalSpeed: 0.009,
    },
    SPEAKING: {
      coreColor: [0.05, 0.6, 1.0],
      rimColor: [0.9, 0.95, 1.0],
      displacement: 0.45,
      noiseSpeed: 2.5,
      noiseScale: 1.8,
      fresnelPower: 1.5,
      intensity: 1.4,
      gimbalSpeed: 0.035,
    },
    SUCCESS: {
      coreColor: [0.2, 0.85, 1.0],
      rimColor: [1.0, 1.0, 1.0],
      displacement: 0.22,
      noiseSpeed: 1.1,
      noiseScale: 1.0,
      fresnelPower: 2.5,
      intensity: 1.3,
      gimbalSpeed: 0.01,
    },
    ERROR: {
      coreColor: [0.9, 0.08, 0.08],
      rimColor: [1.0, 0.4, 0.4],
      displacement: 0.55,
      noiseSpeed: 3.2,
      noiseScale: 2.2,
      fresnelPower: 1.3,
      intensity: 1.5,
      gimbalSpeed: 0.05,
    },
  };

  class JarvisOrbController {
    constructor(containerElement) {
      this.container = containerElement;
      this.currentState = 'IDLE';
      this.spatialMode = 'HOME';
      this.mouseTarget = { x: 0, y: 0 };
      this.mouseCurrent = { x: 0, y: 0 };
      this.clock = new THREE.Clock();

      this.currentConfig = Object.assign({}, ORB_CONFIGS.IDLE);
      this.targetConfig = Object.assign({}, ORB_CONFIGS.IDLE);

      this.initThree();
      this.createOrb();
      this.createGimbals();
      this.createParticles();
      this.setupEvents();
      this.animate = this.animate.bind(this);
      requestAnimationFrame(this.animate);
    }

    initThree() {
      const width = this.container.clientWidth || 380;
      const height = this.container.clientHeight || 380;

      this.scene = new THREE.Scene();
      this.camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
      this.camera.position.z = 7.2;

      this.renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'high-performance' });
      this.renderer.setSize(width, height);
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      this.renderer.domElement.className = 'three-orb-canvas';
      this.container.appendChild(this.renderer.domElement);
    }

    createOrb() {
      const geometry = new THREE.SphereGeometry(2.0, 64, 64);
      this.uniforms = {
        uTime: { value: 0.0 },
        uDisplacement: { value: this.currentConfig.displacement },
        uNoiseScale: { value: this.currentConfig.noiseScale },
        uNoiseSpeed: { value: this.currentConfig.noiseSpeed },
        uCoreColor: { value: new THREE.Color(...this.currentConfig.coreColor) },
        uRimColor: { value: new THREE.Color(...this.currentConfig.rimColor) },
        uFresnelPower: { value: this.currentConfig.fresnelPower },
        uIntensity: { value: this.currentConfig.intensity },
      };

      this.orbMaterial = new THREE.ShaderMaterial({
        vertexShader,
        fragmentShader,
        uniforms: this.uniforms,
        transparent: true,
        blending: THREE.AdditiveBlending,
      });

      this.orbMesh = new THREE.Mesh(geometry, this.orbMaterial);
      this.scene.add(this.orbMesh);
    }

    createGimbals() {
      this.gimbalGroup = new THREE.Group();

      // Outer segmented coordinate ring
      const outerGeo = new THREE.TorusGeometry(3.05, 0.022, 16, 100);
      const outerMat = new THREE.MeshBasicMaterial({
        color: 0x38bdf8,
        transparent: true,
        opacity: 0.28,
        blending: THREE.AdditiveBlending,
      });
      this.outerRing = new THREE.Mesh(outerGeo, outerMat);
      this.gimbalGroup.add(this.outerRing);

      // Inner counter-rotating ring
      const innerGeo = new THREE.TorusGeometry(2.65, 0.018, 16, 80);
      const innerMat = new THREE.MeshBasicMaterial({
        color: 0x0284c7,
        transparent: true,
        opacity: 0.22,
        blending: THREE.AdditiveBlending,
      });
      this.innerRing = new THREE.Mesh(innerGeo, innerMat);
      this.gimbalGroup.add(this.innerRing);

      // Radial marker brackets
      for (let i = 0; i < 4; i++) {
        const bracketGeo = new THREE.BoxGeometry(0.08, 0.35, 0.08);
        const bracketMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.6 });
        const bracket = new THREE.Mesh(bracketGeo, bracketMat);
        const angle = (i * Math.PI) / 2;
        bracket.position.set(Math.cos(angle) * 3.05, Math.sin(angle) * 3.05, 0);
        bracket.rotation.z = angle;
        this.gimbalGroup.add(bracket);
      }

      this.scene.add(this.gimbalGroup);
    }

    createParticles() {
      const count = 350;
      const positions = new Float32Array(count * 3);
      const radius = 4.2;

      for (let i = 0; i < count; i++) {
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.acos(Math.random() * 2 - 1);
        const r = 2.4 + Math.random() * (radius - 2.4);

        positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
        positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
        positions[i * 3 + 2] = r * Math.cos(phi);
      }

      const particleGeo = new THREE.BufferGeometry();
      particleGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));

      const particleMat = new THREE.PointsMaterial({
        color: 0x38bdf8,
        size: 0.045,
        transparent: true,
        opacity: 0.45,
        blending: THREE.AdditiveBlending,
      });

      this.particleSystem = new THREE.Points(particleGeo, particleMat);
      this.scene.add(this.particleSystem);
    }

    setupEvents() {
      window.addEventListener('mousemove', (e) => {
        const normX = (e.clientX / window.innerWidth) * 2 - 1;
        const normY = -(e.clientY / window.innerHeight) * 2 + 1;
        this.mouseTarget.x = normX * 0.45;
        this.mouseTarget.y = normY * 0.45;
      });

      window.addEventListener('resize', () => {
        const width = this.container.clientWidth || 380;
        const height = this.container.clientHeight || 380;
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
      });
    }

    setState(stateName) {
      const upper = (stateName || 'IDLE').toUpperCase();
      if (ORB_CONFIGS[upper]) {
        this.currentState = upper;
        this.targetConfig = Object.assign({}, ORB_CONFIGS[upper]);
      }
    }

    setSpatialMode(mode) {
      this.spatialMode = mode === 'CHAT' ? 'CHAT' : 'HOME';
    }

    animate() {
      requestAnimationFrame(this.animate);

      const delta = this.clock.getDelta();
      const elapsedTime = this.clock.getElapsedTime();

      // Smooth damping toward target uniforms
      const lerpFactor = 0.06;
      this.currentConfig.displacement += (this.targetConfig.displacement - this.currentConfig.displacement) * lerpFactor;
      this.currentConfig.noiseSpeed += (this.targetConfig.noiseSpeed - this.currentConfig.noiseSpeed) * lerpFactor;
      this.currentConfig.fresnelPower += (this.targetConfig.fresnelPower - this.currentConfig.fresnelPower) * lerpFactor;
      this.currentConfig.intensity += (this.targetConfig.intensity - this.currentConfig.intensity) * lerpFactor;
      this.currentConfig.gimbalSpeed += (this.targetConfig.gimbalSpeed - this.currentConfig.gimbalSpeed) * lerpFactor;

      // Update shader uniforms
      this.uniforms.uTime.value = elapsedTime;
      this.uniforms.uDisplacement.value = this.currentConfig.displacement;
      this.uniforms.uNoiseSpeed.value = this.currentConfig.noiseSpeed;
      this.uniforms.uFresnelPower.value = this.currentConfig.fresnelPower;
      this.uniforms.uIntensity.value = this.currentConfig.intensity;

      const targetCore = new THREE.Color(...this.targetConfig.coreColor);
      const targetRim = new THREE.Color(...this.targetConfig.rimColor);
      this.uniforms.uCoreColor.value.lerp(targetCore, lerpFactor);
      this.uniforms.uRimColor.value.lerp(targetRim, lerpFactor);

      // Rotate gimbals
      if (this.outerRing) {
        this.outerRing.rotation.z += this.currentConfig.gimbalSpeed;
        this.outerRing.rotation.x = Math.sin(elapsedTime * 0.4) * 0.25;
      }
      if (this.innerRing) {
        this.innerRing.rotation.z -= this.currentConfig.gimbalSpeed * 1.35;
        this.innerRing.rotation.y = Math.cos(elapsedTime * 0.5) * 0.35;
      }
      if (this.particleSystem) {
        this.particleSystem.rotation.y += 0.002;
      }

      // Mouse Parallax Damping
      this.mouseCurrent.x += (this.mouseTarget.x - this.mouseCurrent.x) * 0.05;
      this.mouseCurrent.y += (this.mouseTarget.y - this.mouseCurrent.y) * 0.05;

      this.scene.rotation.y = this.mouseCurrent.x;
      this.scene.rotation.x = -this.mouseCurrent.y;

      this.renderer.render(this.scene, this.camera);
    }
  }

  // Expose global APIs to window
  window.initJarvisOrb = function (containerId) {
    const el = document.getElementById(containerId);
    if (!el) return null;
    if (window._jarvisOrbInstance) return window._jarvisOrbInstance;
    const controller = new JarvisOrbController(el);
    window._jarvisOrbInstance = controller;
    return controller;
  };

  window.setJarvisOrbState = function (state) {
    if (window._jarvisOrbInstance) {
      window._jarvisOrbInstance.setState(state);
    }
    // Also reflect text in DOM
    const stateEl = document.getElementById('orbStateText');
    if (stateEl) {
      stateEl.textContent = `SYSTEM // ${(state || 'IDLE').toUpperCase()}`;
    }
    const coreBadge = document.getElementById('coreLoopState');
    if (coreBadge) {
      coreBadge.textContent = (state || 'IDLE').toUpperCase();
    }
  };

  window.setJarvisSpatialMode = function (mode) {
    const targetMode = mode === 'CHAT' ? 'CHAT' : 'HOME';
    if (window._jarvisOrbInstance) {
      window._jarvisOrbInstance.setSpatialMode(targetMode);
    }
    const root = document.querySelector('.spatial-viewport');
    if (root) {
      if (targetMode === 'CHAT') {
        root.classList.add('mode-chat');
        root.classList.remove('mode-home');
      } else {
        root.classList.add('mode-home');
        root.classList.remove('mode-chat');
      }
    }
  };
})();
