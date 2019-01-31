import './style.css';
import {atlasView,type Rendered} from './atlas-view';
import {biologyView,coverageView,methodsView,sourcesView,studiesView,subnationalView} from './research-views';
import {download,format,read,safe} from './data';
import {persist,restore} from './state';
import type {Index,State,View} from './types';

const navigation:{id:View;label:string;icon:string}[]=[
  {id:'atlas',label:'Explore the atlas',icon:'◎'},{id:'studies',label:'Study register',icon:'▤'},
  {id:'subnational',label:'Subnational studies',icon:'◫'},{id:'biology',label:'Biological evidence',icon:'⌘'},
  {id:'coverage',label:'Coverage inventory',icon:'▦'},{id:'methods',label:'Methods & models',icon:'⌁'},
  {id:'sources',label:'Source library',icon:'↗'}];
let index:Index,state:State,controller:AbortController|undefined,exportRows:Record<string,unknown>[]=[];
let revision=0;
const app=document.querySelector<HTMLDivElement>('#app')!;

function shell():void {
  app.innerHTML=`<aside class="sidebar"><a class="brand" href="?view=atlas" aria-label="Aftershock Atlas home"><span class="brand-mark">a<span>+</span></span><span>aftershock<strong>ATLAS</strong></span></a><div class="nav-caption">RESEARCH WORKSPACE</div><nav aria-label="Main navigation">${navigation.map(n=>`<button data-view="${n.id}" class="nav-item" aria-label="${n.label}" title="${n.label}"><span aria-hidden="true">${n.icon}</span><span>${n.label}</span></button>`).join('')}</nav><div class="sidebar-bottom"><div class="project-note"><span class="mini-mark">↳</span><p>A record of change.<br>A study of what remains.</p></div><a href="https://github.com/Aneesh495/aftershock-atlas" target="_blank" rel="noreferrer">Source & reproducibility <span>↗</span></a><div class="edition-note">NON-PERSONAL RESEARCH DEMO<br>FULL ACCEPTANCE INCOMPLETE</div></div></aside><div class="main-shell"><header class="topbar"><div class="breadcrumb">Aftershock Atlas <span>/</span> <strong id="current-view">Explore</strong></div><div class="topbar-actions"><span class="snapshot"><i></i>Acquired Nov 11, 2026</span><button id="export" class="export-button" aria-label="Export currently selected data as CSV">↓ <span>Export data</span></button></div></header><main id="workspace" tabindex="-1"><div class="loading">Loading research workspace…</div></main><footer><span>AFTERSHOCK ATLAS <span class="footer-sep">/</span> Population-level research</span><span>Sources have limits. Conclusions should too.</span></footer><div id="announcements" role="status" aria-live="polite" class="sr-only"></div></div>`;
  document.querySelector('#export')!.addEventListener('click',()=>{
    download(exportRows,`aftershock-${state.view}-${state.metric}`);
    document.querySelector('#announcements')!.textContent=`Exported ${exportRows.length} source-bound rows.`;
  });
  bindViews(app);
}

function bindViews(root:HTMLElement):void {
  root.querySelectorAll<HTMLElement>('[data-view]').forEach(button=>button.addEventListener('click',()=>{
    const patch:Partial<State>={view:button.dataset.view as View};
    if(button.dataset.openStudy)patch.study=button.dataset.openStudy;
    update(patch,true);
  }));
}

function update(patch:Partial<State>,focus=false):void {
  const previousFocus=(document.activeElement as HTMLElement)?.id;
  state={...state,...patch};persist(state);void render(focus?undefined:previousFocus,focus);
}

async function render(restoreFocus?:string,moveFocus=false):Promise<void> {
  controller?.abort();controller=new AbortController();const signal=controller.signal,version=++revision;
  const root=document.querySelector<HTMLElement>('#workspace')!;
  root.setAttribute('aria-busy','true');
  app.querySelectorAll<HTMLElement>('.nav-item').forEach(b=>{
    const active=b.dataset.view===state.view;b.classList.toggle('active',active);
    if(active)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');
  });
  document.querySelector('#current-view')!.textContent=navigation.find(n=>n.id===state.view)!.label;
  try {
    let result:Rendered;
    if(state.view==='atlas')result=await atlasView(index,state,signal,update);
    else if(state.view==='studies')result=await studiesView(index,state,signal,update);
    else if(state.view==='coverage')result=await coverageView(index,signal);
    else if(state.view==='biology')result=await biologyView(signal);
    else if(state.view==='subnational')result=await subnationalView(state,signal,update);
    else if(state.view==='sources')result=await sourcesView(signal);
    else result=await methodsView(index,signal);
    if(signal.aborted||version!==revision)return;
    root.innerHTML=result.html;exportRows=result.rows;bindViews(root);
    const exportButton=document.querySelector<HTMLButtonElement>('#export')!;
    exportButton.disabled=!exportRows.length;
    if(result.after)await result.after(root);
    if(signal.aborted||version!==revision)return;
    root.setAttribute('aria-busy','false');
    if(moveFocus){root.focus();root.scrollIntoView({block:'start'});}
    else if(restoreFocus)document.getElementById(restoreFocus)?.focus({preventScroll:true});
    document.querySelector('#announcements')!.textContent=`${navigation.find(n=>n.id===state.view)!.label} loaded. ${format(exportRows.length,0)} exportable rows.`;
  } catch(error) {
    if(signal.aborted)return;
    root.setAttribute('aria-busy','false');
    root.innerHTML=`<section class="panel error-state"><div class="eyebrow">DATA COULD NOT BE LOADED</div><h1>This view is unavailable.</h1><p>${safe(error instanceof Error?error.message:error)}</p><button id="retry" class="export-button">Retry this view</button><p class="micro">Successful data remains cached in this browser session. An unavailable source is never filled with example values.</p></section>`;
    root.querySelector('#retry')!.addEventListener('click',()=>void render());
  }
}

async function start():Promise<void> {
  try {index=await read<Index>('index');state=restore(index);persist(state);shell();await render();}
  catch(error){app.innerHTML=`<main class="startup-error"><h1>Aftershock Atlas</h1><p>The source manifest could not be loaded.</p><pre>${safe(error instanceof Error?error.message:error)}</pre><button onclick="location.reload()">Retry</button></main>`;}
}
void start();
