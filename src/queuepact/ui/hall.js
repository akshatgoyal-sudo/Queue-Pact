// Rendering only: coordinates, identities and progress come from Python.
export default {
  props: {model: Object}, emits: ['select'],
  data() { return {markers: [], frame: null, generation: -1}; },
  watch: {model: {deep: false, handler(next) { this.renderMarkers(next); }}},
  beforeUnmount() { cancelAnimationFrame(this.frame); },
  methods: {
    renderMarkers(next) {
      cancelAnimationFrame(this.frame);
      const fresh = this.generation !== next.generation;
      this.generation = next.generation;
      const targets = next.markers || [];
      const previous = new Map(this.markers.map(m => [m.id, m]));
      if (fresh || !next.playing || next.speed >= 5 || next.reduced_motion || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        this.markers = targets.map(m => ({...m})); return;
      }
      const starts = targets.map(m => previous.get(m.id) || {...m, x: 85, y: 95});
      const start = performance.now();
      const move = now => {
        const t = Math.min(1, (now - start) / 180);
        this.markers = targets.map((m, i) => ({...m, x: starts[i].x + (m.x-starts[i].x)*t, y: starts[i].y + (m.y-starts[i].y)*t}));
        if (t < 1) this.frame = requestAnimationFrame(move);
      };
      this.frame = requestAnimationFrame(move);
    },
    statusColor(s) { return {Serving:'#7c3aed', Available:'#64748b', Closing:'#b45309', Closed:'#dc2626'}[s]; },
  },
  template: `
  <svg class="admission-hall" :viewBox="'0 0 1000 ' + (model.height || 548)" role="group" aria-label="Live admission hall. Select a student marker to open a passport.">
    <defs><pattern id="hall-grid" width="20" height="20" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".7" fill="#dfe5ec"/></pattern></defs>
    <rect width="1000" :height="model.height" rx="18" fill="#f7f9fc"/>
    <rect width="1000" :height="model.height" rx="18" fill="url(#hall-grid)"/>
    <path d="M175 85 L185 85 L185 510" stroke="#cbd5e1" stroke-width="2" stroke-dasharray="5 7" fill="none"/>
    <rect x="18" y="25" width="150" height="112" rx="12" fill="#eef2f7" stroke="#d5deea"/>
    <text x="34" y="52" class="zone-heading">Entrance →</text>
    <text x="34" y="79" class="hall-note">{{ model.not_arrived || 0 }} to arrive</text>
    <text x="34" y="116" class="hall-small">Student reception</text>
    <rect x="18" y="150" width="150" height="180" rx="12" fill="#fffbeb" stroke="#f4d79b"/>
    <text x="34" y="176" class="zone-heading">Preparation</text>
    <text x="34" y="197" class="hall-note">{{ model.preparing || 0 }} preparing</text>
    <text x="34" y="319" class="hall-small">{{ model.extra_preparing ? '+' + model.extra_preparing + ' more' : 'Self-service help' }}</text>
    <rect x="18" :y="model.height-133" width="150" height="104" rx="12" fill="#effaf3" stroke="#b9e4cb"/>
    <text x="34" :y="model.height-102" class="zone-heading">Exit ✓</text>
    <text x="34" :y="model.height-73" class="exit-count">{{ model.completed || 0 }}</text>
    <text x="34" :y="model.height-47" class="hall-note">visits completed</text>
    <g v-for="zone in model.zones" :key="zone.id">
      <rect :x="zone.x" :y="zone.y" :width="zone.width" :height="zone.height" rx="14" :fill="zone.hotspot ? '#fffcf4' : 'white'" :stroke="zone.hotspot ? '#d4a549' : '#dbe3ed'" :stroke-width="zone.hotspot ? 2 : 1"/>
      <text :x="zone.x+16" :y="zone.y+29" class="zone-heading">{{ zone.label }}</text>
      <text :x="zone.x+16" :y="zone.y+50" class="hall-note">{{ zone.waiting }} waiting for this service<tspan v-if="zone.multiplier !== 1"> · {{zone.multiplier}}× duration</tspan></text>
      <text :x="zone.x+16" :y="zone.y+zone.height-63" class="hall-small">Shared waiting area <tspan v-if="zone.extra">· +{{zone.extra}} waiting</tspan><tspan v-if="zone.hotspot"> · HOTSPOT</tspan></text>
    </g>
    <g v-for="desk in model.desks" :key="desk.id" :aria-label="desk.text">
      <title>{{ desk.service }} · {{ desk.text }}{{desk.status === 'Closing' ? ' — finishes current student, no new starts' : ''}}</title>
      <rect :x="desk.x" :y="desk.y" width="108" height="59" rx="8" fill="#f5f7fb" :stroke="statusColor(desk.status)" stroke-opacity=".4"/>
      <text :x="desk.x+9" :y="desk.y+20" class="desk-name">{{desk.label}}</text>
      <text :x="desk.x+9" :y="desk.y+38" class="desk-status" :fill="statusColor(desk.status)">{{desk.status}}</text>
      <rect :x="desk.x+9" :y="desk.y+48" width="90" height="4" rx="2" fill="#e2e8f0"/>
      <rect :x="desk.x+9" :y="desk.y+48" :width="90*desk.progress" height="4" rx="2" :fill="statusColor(desk.status)"/>
    </g>
    <g v-for="marker in markers" :key="marker.id" :transform="'translate('+marker.x+','+marker.y+')'" role="button" tabindex="0" :aria-label="marker.description" @click="$emit('select',marker.id)" @keydown.enter.prevent="$emit('select',marker.id)" @keydown.space.prevent="$emit('select',marker.id)" class="student-marker">
      <title>{{marker.description}}</title>
      <circle v-if="marker.selected" r="19" fill="white" stroke="#0f172a" stroke-width="2"/>
      <circle r="14" :fill="marker.color" stroke="white" stroke-width="2"/>
      <circle cy="-3" r="3.2" fill="white"/>
      <path d="M-5 7 Q-5 0 0 0 Q5 0 5 7" fill="white"/>
      <text y="28" text-anchor="middle" class="token-label">{{marker.label}}</text>
    </g>
  </svg>`,
};
