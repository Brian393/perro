/**
 * Scripted map navigation, exposed as `window.perro` for use from the browser console.
 *
 *   await perro.zoom({center: [41.853, -87.668], from: 11, to: 16, duration: 12});
 *   await perro.go('https://perro.timetochange.today/#/pilsen/default?center=41.850,-87.669&zoom=16.883&layers=mural_tiles&sidebar=true', 6);
 *   await perro.wait(10);
 *
 * Coordinates are [lat, lon], as in map links. Durations are in seconds.
 */
import {fromLonLat} from 'ol/proj';
import {inAndOut, linear} from 'ol/easing';

const wait = seconds =>
  new Promise(resolve => {
    setTimeout(resolve, seconds * 1000);
  });

export function installMapScript(map, router) {
  const view = map.getView();

  /**
   * Zoom from one level to another over `duration` seconds, centered on `center`.
   * `from` jumps there first; leave it out to start from the current zoom.
   * `easing: 'linear'` gives a steady zoom; the default eases in and out.
   */
  function zoom({center, from, to, duration = 5, easing} = {}) {
    view.cancelAnimations();
    if (center) view.setCenter(fromLonLat([center[1], center[0]]));
    if (from != null) view.setZoom(from);
    return new Promise(resolve => {
      view.animate(
        {zoom: to, duration: duration * 1000, easing: easing === 'linear' ? linear : inAndOut},
        () => resolve()
      );
    });
  }

  /**
   * Open a map link (full URL or just the #/... part), animating to its view over `duration` seconds.
   * Layers, sidebar and anything else in the link apply as soon as it opens.
   */
  async function go(link, duration = 0) {
    const hash = link.includes('#') ? link.slice(link.indexOf('#') + 1) : link;
    const [path, queryString = ''] = hash.split('?');
    const query = Object.fromEntries(new URLSearchParams(queryString));
    if (duration > 0) query.fly = String(duration);
    else delete query.fly;
    // A recent pan or zoom marks the route as self-updated; clear it so this link is applied.
    const {meta} = router.currentRoute;
    meta.fromEvent = false;
    // Callback form: older vue-router 3 releases don't return a promise from push().
    await new Promise(resolve => {
      router.push({path, query}, resolve, resolve);
    });
    await wait(duration + 0.1);
  }

  /** Run a list of steps in order: {zoom: {...}}, {go: link, duration}, or {wait: seconds}. */
  function play(steps) {
    const run = step => {
      if (step.zoom) return zoom(step.zoom);
      if (step.go) return go(step.go, step.duration);
      return wait(step.wait || 0);
    };
    return steps.reduce((done, step) => done.then(() => run(step)), Promise.resolve());
  }

  function stop() {
    view.cancelAnimations();
  }

  window.perro = {zoom, go, wait, play, stop, map};
}
