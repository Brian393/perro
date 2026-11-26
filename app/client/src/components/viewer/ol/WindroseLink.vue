<template>
  <span style="display: none"></span>
</template>

<script>
/**
 * Sims Permit Case: the Shiny app in the sidebar drives the map, one chapter (tab) at a time.
 *
 * Enabled by `app.windrose` in app-conf.json:
 *   "windrose": {
 *     "legendLayer": "sims_case",          // legend item; checking it opens the app in the sidebar
 *     "appUrl": "https://.../sims_permit",
 *     "layerName": "perez",                 // clicking this layer's features checks the legend item (shortcut)
 *     "defaultChapter": "monitor",
 *     "chapters": {                         // keys = the app's tab values
 *       "monitor": {"layers": ["windrose_link"], "fit": "reach"},
 *       "justice": {"layers": ["general_iron_poverty", ...], "legendOn": [], "fit": "layers"}
 *     },
 *     "allowedOrigins": ["https://flows.rivertoday.org"],
 *     "devIframeRewrite": {"from": "...", "to": "http://127.0.0.1:8765"}  // vite dev only
 *   }
 * A chapter's "layers" are shown while the chapter is open and hidden otherwise (they are not legend
 * layers). "legendOn" layers are switched on when the chapter opens and then left to the user.
 * "windrose_link" is the wedge layer drawn here from the app's messages.
 * Introduction: if the legend item has "displaySidebarInfo", its sidebar info (written with the map's
 * HTML editor) opens in the sidebar overlay, over the app, when the case opens and when its legend icon
 * is clicked. To edit it, switch the case off and click the legend icon.
 *
 * Messages (window.postMessage), all with type 'perez-windrose':
 *   iframe -> map  {action: 'draw', geojson: FeatureCollection (EPSG:4326)}
 *                  {action: 'clear'}
 *                  {action: 'chapter', chapter: '<tab value>'}
 *                  {action: 'fit', bbox: [w, s, e, n]}       (EPSG:4326)
 *                  {action: 'feature', id: '<feature id>', fly: true}   (show its detail; fly: false = stay put)
 *                  {action: 'overlay', html: '<html>'}   (show it in the sidebar overlay)
 *                  {action: 'close'}                     (the app's close button: uncheck the case)
 *   map -> iframe  {action: 'click', id: '<wedge id>'}
 *                  {action: '<name>'}   (an overlay link with data-app-action="<name>", e.g. 'methods-end')
 * GeoJSON feature properties: kind ('wedge' | 'slice' | 'label' | 'site'), id, fill, stroke, text,
 * hover (short HTML for the hover box), detail (full HTML, shown in the sidebar overlay on click).
 */
import VectorLayer from 'ol/layer/Vector';
import VectorSource from 'ol/source/Vector';
import GeoJSON from 'ol/format/GeoJSON';
import {transformExtent} from 'ol/proj';
import {createEmpty, extend, isEmpty} from 'ol/extent';
import {Style, Fill, Stroke, Text, Circle as CircleStyle} from 'ol/style';
import {mapFields} from 'vuex-map-fields';
import {EventBus} from '../../../EventBus';
import {getHtml} from '../../../utils/Helpers';

const MSG_TYPE = 'perez-windrose';
const WEDGES = 'windrose_link';

export default {
  name: 'windrose-link',
  props: {
    map: {type: Object},
  },
  beforeCreate() {
    // (beforeCreate: the immediate `map` watcher below runs before `created`.)
    // Kept out of `data` on purpose: Vue 2 would try to make them reactive, which
    // throws a SecurityError on a cross-origin window and is costly for OL objects.
    this.layer = null;
    this.caseLayer = null;
    this.isOpen = false;
    this.chapter = null;
    this.lastReach = null;
    this.frameWindow = null;
    this.frameOrigin = null;
    this.fitted = false;
    this.savedVisibility = null; // legend layers' visibility before the case opened
  },
  computed: {
    ...mapFields('map', {
      popup: 'popup',
      mobilePanelState: 'mobilePanelState',
      lastSelectedLayer: 'lastSelectedLayer',
    }),
    ...mapFields('app', {
      sidebarState: 'sidebarState',
      sidebarHtml: 'sidebarHtml',
    }),
    conf() {
      return this.$appConfig.app.windrose || null;
    },
  },
  watch: {
    map: {
      handler(map) {
        if (map && this.conf && !this.layer) this.init();
      },
      immediate: true,
    },
  },
  methods: {
    init() {
      this.layer = new VectorLayer({
        name: WEDGES,
        zIndex: this.conf.zIndex || 95,
        source: new VectorSource({wrapX: false}),
        style: this.styleFn,
        visible: false,
        hoverable: true,
        queryable: false,
        displayInLegend: false,
        // read by Map.vue's hover tooltip
        styleObj: JSON.stringify({hoverBackgroundColor: 'rgba(255,255,255,0.96)', hoverTextColor: '#222'}),
      });
      this.map.addLayer(this.layer);
      window.addEventListener('message', this.onMessage);
      EventBus.$on('switchLocale', this.onLocale);
      EventBus.$on('windrose-intro', this.showIntro);
      EventBus.$on('windrose-to-app', this.toApp);
      // The legend item is created (and re-created on group changes) by Map.vue; follow it.
      const layers = this.map.getLayers();
      layers.on('add', e => this.watchCaseLayer(e.element));
      layers.on('remove', e => {
        if (e.element === this.caseLayer) {
          this.caseLayer = null;
          this.sync();
        }
      });
      layers.forEach(l => this.watchCaseLayer(l));
    },
    watchCaseLayer(layer) {
      if (!this.conf.legendLayer || layer.get('name') !== this.conf.legendLayer || layer === this.caseLayer) return;
      this.caseLayer = layer;
      layer.on('change:visible', () => {
        if (layer === this.caseLayer) this.sync();
      });
      this.sync();
    },
    /** Open or close the app to match the legend checkbox. */
    sync() {
      const on = !!(this.caseLayer && this.caseLayer.getVisible());
      if (on && !this.isOpen) this.open();
      else if (!on && this.isOpen) this.close();
    },
    appUrl() {
      let url = this.conf.appUrl;
      const rewrite = this.conf.devIframeRewrite;
      if (import.meta.env.DEV && rewrite && rewrite.from && rewrite.to && url)
        url = url.split(rewrite.from).join(rewrite.to);
      if (!url) return url;
      // the app shows its texts in the map's language (?lang=en|es)
      const lang = (this.$i18n && this.$i18n.locale) || 'en';
      return `${url}${url.includes('?') ? '&' : '?'}lang=${encodeURIComponent(lang)}`;
    },
    /** Map language switched: reload the open app in the new language. */
    onLocale() {
      if (!this.isOpen) return;
      EventBus.$emit('sidebar-overlay-close');
      this.clear();
      EventBus.$emit('sidebar-app', {url: this.appUrl()});
    },
    showPanel() {
      EventBus.$emit('closePopupInfo');
      EventBus.$emit('sidebar-overlay-close');
      this.sidebarState = true;
      this.mobilePanelState = true;
    },
    open() {
      this.isOpen = true;
      this.hideOthers();
      this.showPanel();
      EventBus.$emit('sidebar-app', {url: this.appUrl()});
      // until the app reports its tab
      this.showChapter(this.conf.defaultChapter || 'monitor');
      this.showIntro();
    },
    /** The legend item's sidebar info (map HTML editor), shown in the overlay over the app. */
    /** Forward a request to the app (e.g. from a link in an overlay page: data-app-action="methods-end"). */
    toApp(msg) {
      if (this.frameWindow && this.frameOrigin)
        this.frameWindow.postMessage({type: MSG_TYPE, ...msg}, this.frameOrigin);
    },
    showIntro() {
      if (!this.isOpen || !this.caseLayer || !this.caseLayer.get('displaySidebarInfo')) return;
      const content = this.sidebarHtml && this.sidebarHtml.layers && this.sidebarHtml.layers[this.conf.legendLayer];
      const html = getHtml(content, this.$appConfig.app.defaultLanguage, this.$i18n.locale);
      if (!html) return;
      this.sidebarState = true;
      this.mobilePanelState = true;
      EventBus.$emit('sidebar-overlay', {html, replace: true});
    },
    close() {
      this.isOpen = false;
      EventBus.$emit('sidebar-app', null);
      EventBus.$emit('sidebar-overlay-close');
      this.chapterLayerNames().forEach(name => this.setLayerVisible(name, false));
      this.clear();
      this.chapter = null;
      // the case's sidebar info was selected when it opened (Legend); without the app it would show alone
      if (this.lastSelectedLayer === this.conf.legendLayer) this.lastSelectedLayer = null;
      this.restoreOthers();
    },
    /** The case opens on a clean map: the other legend layers are switched off (the user can switch them back on). */
    hideOthers() {
      this.savedVisibility = {};
      this.map.getLayers().forEach(l => {
        const name = l.get('name');
        if (!name || l === this.caseLayer || l === this.layer || !l.get('displayInLegend')) return;
        this.savedVisibility[name] = l.getVisible();
        l.setVisible(false);
      });
      EventBus.$emit('legend-refresh');
    },
    /** When the case closes, the other legend layers return to how they were before it opened. */
    restoreOthers() {
      const saved = this.savedVisibility;
      this.savedVisibility = null;
      if (!saved) return;
      this.map.getLayers().forEach(l => {
        const name = l.get('name');
        if (name in saved) l.setVisible(saved[name]);
      });
      EventBus.$emit('legend-refresh');
    },
    /** Shortcut from the map (click on the Perez monitor): check the legend item, or just bring the panel back. */
    openCase() {
      if (!this.caseLayer) return false;
      if (!this.caseLayer.getVisible()) this.caseLayer.setVisible(true);
      else this.showPanel();
      return true;
    },
    isCaseTrigger(layer) {
      return !!(this.conf && this.conf.legendLayer && layer && layer.get('name') === this.conf.layerName);
    },
    chapterLayerNames() {
      const names = new Set([WEDGES]);
      Object.values(this.conf.chapters || {}).forEach(c => (c.layers || []).forEach(n => names.add(n)));
      return [...names];
    },
    findLayer(name) {
      if (name === WEDGES) return this.layer;
      let found = null;
      const search = layers =>
        layers.forEach(l => {
          if (found) return;
          if (l.get('name') === name) found = l;
          else if (l.getLayers) search(l.getLayers().getArray());
        });
      search(this.map.getLayers().getArray());
      return found;
    },
    setLayerVisible(name, visible) {
      const layer = this.findLayer(name);
      if (layer) layer.setVisible(visible);
    },
    showChapter(name) {
      const chapter = (this.conf.chapters || {})[name] || {layers: []};
      const shown = chapter.layers || [];
      const changed = name !== this.chapter;
      this.chapter = name;
      this.chapterLayerNames().forEach(n => this.setLayerVisible(n, shown.includes(n)));
      if (!changed) return;
      (chapter.legendOn || []).forEach(n => this.setLayerVisible(n, true));
      EventBus.$emit('sidebar-overlay-close');
      if (chapter.fit === 'layers') this.fitLayers(shown);
      else if (chapter.fit === 'reach' && this.lastReach) this.fitBbox(this.lastReach);
    },
    onMessage(event) {
      const data = event.data;
      if (!data || data.type !== MSG_TYPE || !this.layer) return;
      if (!(this.conf.allowedOrigins || []).includes(event.origin)) return;
      if (!this.isOpen) return;
      this.frameWindow = event.source;
      this.frameOrigin = event.origin;
      if (data.action === 'clear') {
        this.layer.getSource().clear();
      } else if (data.action === 'draw' && data.geojson) {
        this.draw(data.geojson);
      } else if (data.action === 'chapter' && typeof data.chapter === 'string') {
        this.showChapter(data.chapter);
      } else if (data.action === 'fit' && Array.isArray(data.bbox)) {
        this.fitBbox(data.bbox);
      } else if (data.action === 'feature' && typeof data.id === 'string') {
        EventBus.$emit('sidebar-overlay-feature', data.id, data.fly !== false);
      } else if (data.action === 'close') {
        // the app's close button: uncheck the legend item, which closes the case (see sync)
        if (this.caseLayer) this.caseLayer.setVisible(false);
        EventBus.$emit('legend-refresh');
      } else if (data.action === 'overlay' && typeof data.html === 'string' && data.html) {
        // details sent by the app (e.g. a block group's data) open in the sidebar overlay, over the app
        this.sidebarState = true;
        EventBus.$emit('sidebar-overlay', {html: data.html, replace: true});
      }
    },
    draw(geojson) {
      // Group changes remove all map layers; put ours back if needed.
      if (!this.map.getLayers().getArray().includes(this.layer)) this.map.addLayer(this.layer);
      const features = new GeoJSON().readFeatures(geojson, {
        dataProjection: 'EPSG:4326',
        featureProjection: this.map.getView().getProjection(),
      });
      features.forEach(f => {
        if (f.get('hover')) f.set('hoverAttribute', f.get('hover'));
      });
      const source = this.layer.getSource();
      source.clear();
      source.addFeatures(features);
      if (Array.isArray(geojson.reach_extent) && geojson.reach_extent.length === 4)
        this.lastReach = geojson.reach_extent;
      // fit once per opening, and again whenever the app asks (e.g. it switched monitors), if the wedges are showing
      if ((!this.fitted || geojson.fit === true) && features.length && this.layer.getVisible() && this.lastReach) {
        this.fitted = true;
        this.fitBbox(this.lastReach);
      }
    },
    fitExtent(extent) {
      if (!extent || isEmpty(extent)) return;
      // the map may still be resizing (sidebar opening, mobile bottom sheet); fit once it settles
      setTimeout(() => {
        this.map.updateSize();
        this.map.getView().fit(extent, {padding: [30, 30, 30, 30], duration: 600});
      }, 350);
    },
    fitBbox(bbox) {
      if (!Array.isArray(bbox) || bbox.length !== 4 || bbox.some(v => typeof v !== 'number')) return;
      this.fitExtent(transformExtent(bbox, 'EPSG:4326', this.map.getView().getProjection()));
    },
    /** Fit to the features of these layers; layers not loaded yet (they load when first shown) are waited for. */
    fitLayers(names) {
      const sources = names
        .map(n => this.findLayer(n))
        .filter(l => l && l.getSource && l.getSource() && l.getSource().getFeatures)
        .map(l => l.getSource());
      const fit = () => {
        const extent = createEmpty();
        sources.forEach(s => {
          if (s.getFeatures().length) extend(extent, s.getExtent());
        });
        this.fitExtent(extent);
      };
      const pending = sources.filter(s => !s.getFeatures().length);
      if (!pending.length) fit();
      else pending.forEach(s => s.once('featuresloadend', fit));
    },
    clear() {
      if (this.layer) this.layer.getSource().clear();
      this.frameWindow = null;
      this.frameOrigin = null;
      this.fitted = false;
    },
    /**
     * Called first by Map.vue's click handler. Returns true when the click hit a
     * wedge, so the map does not treat it as a click on empty map.
     */
    handleMapClick(evt) {
      if (!this.layer || !this.layer.getVisible() || !this.layer.getSource().getFeatures().length) return false;
      let hit;
      let wedge;
      this.map.forEachFeatureAtPixel(
        evt.pixel,
        f => {
          if (!hit) hit = f;
          if (!wedge && f.get('id')) wedge = f;
        },
        {layerFilter: l => l === this.layer, hitTolerance: 2}
      );
      // Any hit on this layer (wedge, label, site dot) is ours: never close the panel.
      if (!hit) return false;
      // Full numbers (detail) go into the sidebar overlay; the hover keeps only a short line.
      const withDetail = [hit, wedge].find(f => f && f.get('detail'));
      if (withDetail) EventBus.$emit('sidebar-overlay', {html: withDetail.get('detail'), replace: true});
      // A site dot on top of a wedge is just a site click (its info shows on hover).
      if (hit.get('kind') !== 'site' && wedge && this.frameWindow && this.frameOrigin) {
        this.frameWindow.postMessage({type: MSG_TYPE, action: 'click', id: wedge.get('id')}, this.frameOrigin);
      }
      return true;
    },
    styleFn(feature) {
      const kind = feature.get('kind');
      if (kind === 'site') {
        return new Style({
          zIndex: 10,
          image: new CircleStyle({
            radius: 5,
            fill: new Fill({color: '#111111'}),
            stroke: new Stroke({color: '#ffffff', width: 1.5}),
          }),
        });
      }
      if (kind === 'label') {
        return new Style({
          text: new Text({
            text: feature.get('text'),
            font: 'bold 12px sans-serif',
            fill: new Fill({color: feature.get('stroke') || '#8c0c14'}),
            backgroundFill: new Fill({color: 'rgba(255,255,255,0.85)'}),
            padding: [0, 2, 0, 2],
          }),
        });
      }
      return new Style({
        fill: new Fill({color: feature.get('fill') || 'rgba(208,34,43,0.35)'}),
        stroke: new Stroke({
          color: feature.get('stroke') || '#8c0c14',
          width: kind === 'slice' ? 1 : 1.2,
        }),
      });
    },
  },
  beforeDestroy() {
    window.removeEventListener('message', this.onMessage);
    EventBus.$off('switchLocale', this.onLocale);
    EventBus.$off('windrose-intro', this.showIntro);
    EventBus.$off('windrose-to-app', this.toApp);
    if (this.map && this.layer) this.map.removeLayer(this.layer);
  },
};
</script>
