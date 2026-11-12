import {initPlayground} from "./playground.js";
initPlayground({document, fetch: globalThis.fetch.bind(globalThis), clipboard: navigator.clipboard});
