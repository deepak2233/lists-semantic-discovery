import {initPlayground} from "./playground.js";
import {initComparison} from "./comparison.js";
initPlayground({document, fetch: globalThis.fetch.bind(globalThis), clipboard: navigator.clipboard});
initComparison({document, fetch: globalThis.fetch.bind(globalThis)});
