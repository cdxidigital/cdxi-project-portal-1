import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  Shield, Globe, Cpu, Briefcase, MessageSquare, CheckCircle2, ArrowRight,
  Clock, BellRing, History, CheckCircle, Layers, Tag, Receipt, Lock,
  FileSignature, DollarSign, ChevronRight, FolderKanban, Handshake,
  Compass, Trophy, ShieldCheck, LogOut, Plus, Trash2, AlertCircle
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const TIER_ICONS = { navigator: Compass, partner: Handshake, council: Trophy };

const App = () => {
  // Auth
  const [authMode, setAuthMode] = useState('none'); // 'none' | 'client' | 'consultant'
  const [token, setToken] = useState(() => localStorage.getItem('cdxi_token') || '');
  const [pin, setPin] = useState('');
  const [authError, setAuthError] = useState(false);
  const [verifying, setVerifying] = useState(false);

  // App
  const [activeTab, setActiveTab] = useState('command');
  const [state, setState] = useState({
    role: 'client', nda_accepted: false, eaa_selection: null,
    strategic_reserve: 150, active_balance: 150, total_expenses: 0,
  });
  const [projects, setProjects] = useState([]);
  const [milestones, setMilestones] = useState([]);
  const [eaaModels, setEaaModels] = useState([]);
  const [expenses, setExpenses] = useState([]);
  const [newExpense, setNewExpense] = useState({ desc: '', amount: '' });
  const [filterProject, setFilterProject] = useState('All');

  // Urgent
  const [showUrgentModal, setShowUrgentModal] = useState(false);
  const [urgentMessage, setUrgentMessage] = useState('');
  const [isSent, setIsSent] = useState(false);
  const [sending, setSending] = useState(false);

  const authClient = useCallback(() => {
    const inst = axios.create({ baseURL: API });
    if (token) inst.defaults.headers.common.Authorization = `Bearer ${token}`;
    return inst;
  }, [token]);

  const loadAll = useCallback(async () => {
    if (!token) return;
    const api = authClient();
    try {
      const [s, p, m, e, eaa] = await Promise.all([
        api.get('/state'),
        api.get('/projects'),
        api.get('/milestones'),
        api.get('/expenses'),
        api.get('/eaa/models'),
      ]);
      setState(s.data);
      setProjects(p.data);
      setMilestones(m.data);
      setExpenses(e.data);
      setEaaModels(eaa.data);
      setAuthMode(s.data.role);
    } catch (err) {
      if (err.response?.status === 401) {
        localStorage.removeItem('cdxi_token');
        setToken('');
        setAuthMode('none');
      }
    }
  }, [token, authClient]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const handlePinInput = async (val) => {
    if (verifying || pin.length >= 4) return;
    const newPin = pin + val;
    setPin(newPin);
    if (newPin.length === 4) {
      setVerifying(true);
      try {
        const res = await axios.post(`${API}/auth/verify-pin`, { pin: newPin });
        localStorage.setItem('cdxi_token', res.data.token);
        setToken(res.data.token);
        setAuthMode(res.data.role);
        setAuthError(false);
      } catch {
        setAuthError(true);
        setTimeout(() => { setPin(''); setAuthError(false); }, 800);
      } finally {
        setVerifying(false);
      }
    }
  };

  const handleLogout = async () => {
    try { await authClient().post('/auth/logout'); } catch (_) {}
    localStorage.removeItem('cdxi_token');
    setToken('');
    setAuthMode('none');
    setPin('');
    setActiveTab('command');
  };

  const handleAcceptNda = async () => {
    await authClient().post('/nda/accept');
    await loadAll();
  };

  const handleUrgentSignal = async () => {
    if (!urgentMessage.trim() || sending) return;
    setSending(true);
    try {
      await authClient().post('/urgent-signal', { message: urgentMessage });
      setIsSent(true);
      setTimeout(() => {
        setIsSent(false);
        setShowUrgentModal(false);
        setUrgentMessage('');
      }, 1800);
    } finally { setSending(false); }
  };

  const addExpense = async (e) => {
    e.preventDefault();
    if (!newExpense.desc || !newExpense.amount) return;
    await authClient().post('/expenses', {
      desc: newExpense.desc,
      amount: parseFloat(newExpense.amount),
    });
    setNewExpense({ desc: '', amount: '' });
    await loadAll();
  };

  const removeExpense = async (id) => {
    await authClient().delete(`/expenses/${id}`);
    await loadAll();
  };

  const selectEaa = async (tierId) => {
    await authClient().post('/eaa/select', { tier_id: tierId });
    await loadAll();
  };

  const isAuthorized = authMode !== 'none' && !!token;
  const bypassNda = authMode === 'consultant';
  const ndaUnlocked = state.nda_accepted || bypassNda;

  const calculateNet = (price) => Math.max(0, price - state.active_balance);

  const filteredMilestones = filterProject === 'All'
    ? milestones
    : milestones.filter((m) => m.project === filterProject);

  // ---------- LOGIN SCREEN ----------
  if (!isAuthorized) {
    return (
      <div data-testid="auth-screen" className="min-h-screen bg-slate-100 flex items-center justify-center p-4 font-sans relative overflow-hidden">
        <div className="absolute top-0 right-0 -mr-32 -mt-32 w-96 h-96 rounded-full bg-blue-500/10 blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 left-0 -ml-32 -mb-32 w-96 h-96 rounded-full bg-indigo-500/10 blur-3xl pointer-events-none" />
        <style>{`@import url('https://fonts.googleapis.com/css2?family=Righteous&family=Inter:wght@400;500;600;700&display=swap');
          .righteous{font-family:'Righteous',cursive;} .font-sans{font-family:'Inter',sans-serif;}
          .glass-auth{background:rgba(255,255,255,0.85);backdrop-filter:blur(12px);border:1px solid rgba(255,255,255,0.5);}
          .auth-error{animation:shake 0.4s ease-in-out;}
          @keyframes shake{0%,100%{transform:translateX(0);}25%{transform:translateX(-5px);}75%{transform:translateX(5px);}}`}</style>

        <div className={`w-full max-w-sm glass-auth p-10 rounded-3xl text-center space-y-8 shadow-xl relative z-10 ${authError ? 'auth-error border-red-400' : ''}`}>
          <div className="space-y-2">
            <span className="righteous text-6xl text-blue-700 tracking-tight">cdxi</span>
            <p className="text-xs font-semibold uppercase tracking-widest text-slate-400">Security Node</p>
          </div>
          <div data-testid="pin-dots" className="flex justify-center gap-4 py-2">
            {[0,1,2,3].map((i) => (
              <div key={i} className={`w-3 h-3 rounded-full transition-all duration-200 ${pin.length > i ? 'bg-blue-600 shadow-[0_0_8px_rgba(37,99,235,0.6)]' : 'bg-slate-200'}`} />
            ))}
          </div>
          <div className="grid grid-cols-3 gap-3 max-w-[240px] mx-auto">
            {[1,2,3,4,5,6,7,8,9].map((n) => (
              <button key={n} data-testid={`pin-key-${n}`} disabled={verifying}
                onClick={() => handlePinInput(n.toString())}
                className="h-14 rounded-2xl bg-white border border-slate-100 text-xl font-semibold text-slate-700 hover:bg-blue-50 hover:text-blue-700 hover:border-blue-200 transition-colors shadow-sm active:scale-95 disabled:opacity-50">{n}</button>
            ))}
            <div />
            <button data-testid="pin-key-0" disabled={verifying} onClick={() => handlePinInput('0')}
              className="h-14 rounded-2xl bg-white border border-slate-100 text-xl font-semibold text-slate-700 hover:bg-blue-50 hover:text-blue-700 hover:border-blue-200 transition-colors shadow-sm active:scale-95 disabled:opacity-50">0</button>
            <button data-testid="pin-clear" onClick={() => setPin('')}
              className="h-14 rounded-2xl flex items-center justify-center text-xs font-bold text-slate-400 hover:text-red-500 transition-colors active:scale-95">CLR</button>
          </div>
          {authError && (
            <p data-testid="auth-error-msg" className="text-xs font-semibold text-red-500">Invalid PIN</p>
          )}
        </div>
      </div>
    );
  }

  // ---------- AUTHORIZED PORTAL ----------
  return (
    <div data-testid="portal-root" className="min-h-screen bg-slate-50 text-slate-800 font-sans pb-12 overflow-x-hidden">
      <style>{`@import url('https://fonts.googleapis.com/css2?family=Righteous&family=Inter:wght@400;500;600;700&display=swap');
        .righteous{font-family:'Righteous',cursive;} .font-sans{font-family:'Inter',sans-serif;}
        .glass-nav{background:rgba(255,255,255,0.9);backdrop-filter:blur(12px);border-bottom:1px solid rgba(226,232,240,0.8);}`}</style>

      {/* Urgent Modal */}
      {showUrgentModal && (
        <div data-testid="urgent-modal" className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="bg-white rounded-3xl w-full max-w-md overflow-hidden shadow-2xl border border-slate-200">
            <div className="bg-red-50 border-b border-red-100 p-6 flex justify-between items-center">
              <div className="flex items-center gap-3 text-red-600">
                <BellRing className="w-5 h-5 animate-pulse" />
                <h3 className="font-bold tracking-tight">Priority Signal</h3>
              </div>
              <button data-testid="urgent-close" onClick={() => setShowUrgentModal(false)}
                className="text-slate-400 hover:text-red-600 transition-colors">
                <LogOut className="w-5 h-5 rotate-180" />
              </button>
            </div>
            <div className="p-6 space-y-4">
              {isSent ? (
                <div data-testid="urgent-sent" className="py-8 text-center space-y-4">
                  <CheckCircle className="w-12 h-12 text-emerald-500 mx-auto" />
                  <p className="font-bold text-emerald-600 text-sm">Signal Transmitted</p>
                </div>
              ) : (
                <>
                  <textarea data-testid="urgent-textarea" value={urgentMessage}
                    onChange={(e) => setUrgentMessage(e.target.value)}
                    placeholder="State the nature of the advisory requirement..."
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl p-4 text-sm h-32 outline-none focus:ring-2 focus:ring-red-100 transition-all resize-none placeholder:text-slate-400" />
                  <button data-testid="urgent-submit" onClick={handleUrgentSignal}
                    disabled={!urgentMessage.trim() || sending}
                    className="w-full bg-red-600 text-white py-3.5 rounded-xl font-bold text-sm hover:bg-red-700 transition-all shadow-md shadow-red-100 disabled:opacity-50">
                    {sending ? 'Transmitting...' : 'Initiate Signal'}
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <header className="glass-nav sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-6 py-4 flex justify-between items-center">
          <div className="flex items-center space-x-6">
            <span className="righteous text-3xl text-blue-700">cdxi</span>
            <div className="h-6 w-[1px] bg-slate-200 hidden md:block" />
            <span className="text-xs font-semibold text-slate-500 hidden md:block">Partner Portal</span>
          </div>
          <div className="flex items-center space-x-6 md:space-x-8">
            <nav className="hidden md:flex space-x-6 text-sm font-medium">
              <button data-testid="tab-command" onClick={() => setActiveTab('command')}
                className={`${activeTab === 'command' ? 'text-blue-600' : 'text-slate-500 hover:text-slate-900'} transition-colors`}>Command</button>
              <button data-testid="tab-eea" onClick={() => setActiveTab('eea')}
                className={`${activeTab === 'eea' ? 'text-blue-600' : 'text-slate-500 hover:text-slate-900'} transition-colors`}>Retainer</button>
              <button data-testid="tab-ledger" onClick={() => ndaUnlocked && setActiveTab('ledger')}
                className={`${activeTab === 'ledger' ? 'text-blue-600' : ndaUnlocked ? 'text-slate-500 hover:text-slate-900' : 'text-slate-300 pointer-events-none'} transition-colors flex items-center gap-1.5`}>
                {!ndaUnlocked && <Lock className="w-3 h-3" />} Ledger
              </button>
              <button data-testid="tab-timeline" onClick={() => ndaUnlocked && setActiveTab('timeline')}
                className={`${activeTab === 'timeline' ? 'text-blue-600' : ndaUnlocked ? 'text-slate-500 hover:text-slate-900' : 'text-slate-300 pointer-events-none'} transition-colors flex items-center gap-1.5`}>
                {!ndaUnlocked && <Lock className="w-3 h-3" />} Roadmap
              </button>
            </nav>
            <div className="flex items-center gap-3">
              <button data-testid="urgent-open" onClick={() => setShowUrgentModal(true)}
                className="px-4 py-2 rounded-lg bg-red-50 text-red-600 text-xs font-bold hover:bg-red-100 transition-colors">Urgent</button>
              <button data-testid="logout-btn" onClick={handleLogout}
                className="p-2 text-slate-400 hover:text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors">
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
        <div className="md:hidden border-t border-slate-200 bg-white/50 px-4 py-2 flex justify-between overflow-x-auto">
          <button onClick={() => setActiveTab('command')} className={`px-3 py-1.5 text-xs font-medium rounded-md ${activeTab === 'command' ? 'bg-blue-50 text-blue-600' : 'text-slate-600'}`}>Command</button>
          <button onClick={() => setActiveTab('eea')} className={`px-3 py-1.5 text-xs font-medium rounded-md ${activeTab === 'eea' ? 'bg-blue-50 text-blue-600' : 'text-slate-600'}`}>Retainer</button>
          <button onClick={() => ndaUnlocked && setActiveTab('ledger')} className={`px-3 py-1.5 text-xs font-medium rounded-md ${activeTab === 'ledger' ? 'bg-blue-50 text-blue-600' : ndaUnlocked ? 'text-slate-600' : 'text-slate-400'}`}>Ledger</button>
          <button onClick={() => ndaUnlocked && setActiveTab('timeline')} className={`px-3 py-1.5 text-xs font-medium rounded-md ${activeTab === 'timeline' ? 'bg-blue-50 text-blue-600' : ndaUnlocked ? 'text-slate-600' : 'text-slate-400'}`}>Roadmap</button>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8 md:py-12">
        {/* COMMAND */}
        {activeTab === 'command' && (
          <div data-testid="view-command" className="space-y-12">
            <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-xs font-semibold text-blue-600 bg-blue-50 w-fit px-3 py-1 rounded-full mb-2">
                  <ShieldCheck className="w-3 h-3" />
                  {authMode === 'consultant' ? 'Principal Access' : 'Client Access'}
                </div>
                <h1 className="text-3xl md:text-5xl font-bold text-slate-900 tracking-tight">Partner Command</h1>
                <p className="text-slate-500 text-sm md:text-base max-w-2xl">
                  Strategic oversight portal. Orchestrating brand intelligence, critical infrastructure, and operations.
                </p>
              </div>
            </div>

            {/* NDA gate (client only) */}
            {!state.nda_accepted && authMode === 'client' && (
              <div data-testid="nda-gate" className="bg-white border border-blue-100 p-8 md:p-12 rounded-3xl shadow-lg shadow-blue-900/5 text-center space-y-6 relative overflow-hidden">
                <div className="absolute -right-10 -top-10 text-blue-50 opacity-50">
                  <FileSignature className="w-64 h-64" />
                </div>
                <div className="relative z-10 flex flex-col items-center max-w-2xl mx-auto">
                  <div className="w-16 h-16 bg-blue-50 border border-blue-100 rounded-2xl flex items-center justify-center text-blue-600 mb-4">
                    <Lock className="w-8 h-8" />
                  </div>
                  <h3 className="text-2xl font-bold text-slate-900 mb-2">Master NDA Protocol</h3>
                  <p className="text-slate-500 mb-6">
                    Mandatory confidentiality protocols must be established to initialize tactical nodes and decrypt the partner ledger.
                  </p>
                  <div className="w-full bg-slate-50 border border-slate-200 rounded-xl p-6 text-xs text-slate-500 text-left h-40 overflow-y-auto font-mono mb-6 shadow-inner">
                    SECTION 1: MUTUAL NON-DISCLOSURE AGREEMENT<br/><br/>
                    1.1 Purpose: The Parties agree to collaborate on the development of a peer-to-peer equipment hire marketplace and associated advisory services...<br/><br/>
                    1.2 Confidential Information: Includes business models, source code, wireframes, pricing structures, financial projections, and commercial strategies...<br/><br/>
                    1.3 Obligations: Each Party shall hold all Confidential Information in strict trust and shall not disclose it to any third party without prior written consent.
                  </div>
                  <button data-testid="nda-accept" onClick={handleAcceptNda}
                    className="px-8 py-3.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-semibold transition-colors shadow-md active:scale-95">
                    Accept &amp; Initialize Partner Node
                  </button>
                </div>
              </div>
            )}

            {ndaUnlocked && (
              <>
                {/* Service capabilities strip */}
                <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                  {[
                    { name: 'Brand', icon: Globe },
                    { name: 'PR', icon: MessageSquare },
                    { name: 'ICT', icon: Cpu },
                    { name: 'InfoSec', icon: Shield },
                    { name: 'Strategy', icon: Briefcase },
                  ].map((c) => (
                    <div key={c.name} className="bg-white border border-slate-200 rounded-2xl p-4 flex flex-col items-center text-center gap-2">
                      <c.icon className="w-5 h-5 text-blue-600" />
                      <span className="text-xs font-semibold text-slate-600">{c.name}</span>
                    </div>
                  ))}
                </div>

                {/* Project nodes */}
                <div data-testid="project-grid" className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {projects.map((p) => (
                    <div key={p.id} data-testid={`project-${p.id}`}
                      className="bg-white p-6 rounded-2xl border border-slate-200 hover:border-blue-300 hover:shadow-lg transition-all group flex flex-col">
                      <div className="flex justify-between items-start mb-6">
                        <div className="p-3 bg-slate-50 text-slate-500 rounded-xl group-hover:bg-blue-50 group-hover:text-blue-600 transition-colors">
                          <FolderKanban className="w-6 h-6" />
                        </div>
                        <span className={`text-xs font-semibold px-2.5 py-1 rounded-md border ${p.status === 'Active' ? 'bg-emerald-50 text-emerald-700 border-emerald-100' : 'bg-slate-50 text-slate-600 border-slate-200'}`}>
                          {p.status}
                        </span>
                      </div>
                      <h4 className="text-lg font-bold text-slate-900 mb-1">{p.name}</h4>
                      <p className="text-sm text-slate-500 mb-6">{p.type}</p>
                      <button onClick={() => setActiveTab('timeline')}
                        className="mt-auto pt-4 border-t border-slate-100 w-full flex items-center justify-between text-sm font-medium text-slate-600 group-hover:text-blue-600 transition-colors">
                        View Roadmap <ChevronRight className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        {/* RETAINER / EAA */}
        {activeTab === 'eea' && (
          <div data-testid="view-eea" className="space-y-12">
            <div className="space-y-2">
              <h2 className="text-3xl font-bold text-slate-900 tracking-tight">Executive Advisory</h2>
              <p className="text-slate-500">Engagement structures designed for sustained strategic counsel.</p>
            </div>

            <div className="bg-blue-50/60 border border-blue-100 rounded-2xl p-5 flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-blue-600 mt-0.5 flex-shrink-0" />
              <div className="text-sm text-slate-700">
                Active strategic balance{' '}
                <span className="font-bold text-blue-700">${state.active_balance.toFixed(2)}</span>{' '}
                will be netted against the selected tier on initiation.
              </div>
            </div>

            <div className="grid md:grid-cols-3 gap-6 lg:gap-8">
              {eaaModels.map((m) => {
                const Icon = TIER_ICONS[m.id] || Compass;
                const selected = state.eaa_selection === m.id;
                const net = calculateNet(m.price);
                return (
                  <div key={m.id} data-testid={`eaa-card-${m.id}`}
                    className={`bg-white p-8 rounded-3xl border flex flex-col relative transition-all ${m.recommended ? 'border-blue-300 shadow-xl shadow-blue-900/5 ring-1 ring-blue-50 md:-mt-4 md:mb-4' : 'border-slate-200 shadow-sm'} ${selected ? 'ring-2 ring-emerald-400' : ''}`}>
                    {m.recommended && (
                      <span className="absolute -top-3.5 left-1/2 -translate-x-1/2 bg-blue-600 text-white text-xs font-bold px-4 py-1 rounded-full shadow-md">
                        Flagship
                      </span>
                    )}
                    {selected && (
                      <span className="absolute -top-3.5 right-4 bg-emerald-500 text-white text-xs font-bold px-3 py-1 rounded-full shadow-md flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3" /> Selected
                      </span>
                    )}
                    <div className="flex items-center gap-4 mb-6">
                      <div className={`p-3 rounded-xl ${m.recommended ? 'bg-blue-100 text-blue-700' : 'bg-slate-100 text-slate-600'}`}>
                        <Icon className="w-6 h-6" />
                      </div>
                      <h4 className="text-xl font-bold text-slate-900 tracking-tight">{m.name}</h4>
                    </div>
                    <div className="mb-4">
                      <div className="flex items-baseline gap-1">
                        <span className="text-4xl font-bold text-slate-900">${m.price.toLocaleString()}</span>
                        <span className="text-sm text-slate-400">/mo</span>
                      </div>
                      <div className="text-xs text-slate-500 mt-1 flex items-center gap-1.5">
                        <Clock className="w-3 h-3" /> {m.hours} delivery hours included
                      </div>
                    </div>
                    <p className="text-sm text-slate-500 mb-6">{m.desc}</p>
                    <ul className="space-y-3 mb-8 flex-1">
                      {m.features.map((f, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-slate-600">
                          <CheckCircle2 className="w-4 h-4 text-emerald-500 flex-shrink-0 mt-0.5" />
                          <span>{f}</span>
                        </li>
                      ))}
                    </ul>
                    {state.active_balance > 0 && (
                      <div className="text-xs text-slate-500 bg-slate-50 border border-slate-100 rounded-lg p-3 mb-4">
                        Net of reserve: <span className="font-bold text-slate-800">${net.toLocaleString()}</span>
                      </div>
                    )}
                    <button data-testid={`select-eaa-${m.id}`} onClick={() => selectEaa(m.id)}
                      disabled={selected}
                      className={`w-full py-3 rounded-xl font-semibold text-sm transition-all flex items-center justify-center gap-2 ${selected ? 'bg-emerald-50 text-emerald-700 cursor-default' : m.recommended ? 'bg-blue-600 text-white hover:bg-blue-700 shadow-md' : 'bg-slate-900 text-white hover:bg-slate-800'}`}>
                      {selected ? <>Active Tier</> : <>Select Tier <ArrowRight className="w-4 h-4" /></>}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* LEDGER */}
        {activeTab === 'ledger' && ndaUnlocked && (
          <div data-testid="view-ledger" className="space-y-10">
            <div className="space-y-2">
              <h2 className="text-3xl font-bold text-slate-900 tracking-tight">Strategic Ledger</h2>
              <p className="text-slate-500">Reserve allocation and project burn against the master account.</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div data-testid="ledger-reserve" className="bg-gradient-to-br from-blue-600 to-indigo-700 text-white rounded-2xl p-6 shadow-xl shadow-blue-900/10">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-semibold uppercase tracking-widest opacity-70">Strategic Reserve</span>
                  <DollarSign className="w-4 h-4 opacity-60" />
                </div>
                <div className="text-3xl font-bold tracking-tight">${state.strategic_reserve.toFixed(2)}</div>
                <div className="text-xs opacity-70 mt-1">Pre-funded retainer credit</div>
              </div>
              <div data-testid="ledger-balance" className="bg-white border border-slate-200 rounded-2xl p-6">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-semibold uppercase tracking-widest text-slate-400">Active Balance</span>
                  <Layers className="w-4 h-4 text-slate-400" />
                </div>
                <div className="text-3xl font-bold tracking-tight text-emerald-600">${state.active_balance.toFixed(2)}</div>
                <div className="text-xs text-slate-500 mt-1">Available against next tier</div>
              </div>
              <div data-testid="ledger-burn" className="bg-white border border-slate-200 rounded-2xl p-6">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-semibold uppercase tracking-widest text-slate-400">Total Burn</span>
                  <Receipt className="w-4 h-4 text-slate-400" />
                </div>
                <div className="text-3xl font-bold tracking-tight text-slate-900">${state.total_expenses.toFixed(2)}</div>
                <div className="text-xs text-slate-500 mt-1">{expenses.length} entr{expenses.length === 1 ? 'y' : 'ies'} logged</div>
              </div>
            </div>

            <div className="bg-white border border-slate-200 rounded-2xl p-6 md:p-8">
              <h3 className="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
                <Plus className="w-4 h-4 text-blue-600" /> Log Expense
              </h3>
              <form onSubmit={addExpense} className="grid grid-cols-1 md:grid-cols-12 gap-3">
                <input data-testid="expense-desc" type="text" value={newExpense.desc}
                  onChange={(e) => setNewExpense({ ...newExpense, desc: e.target.value })}
                  placeholder="Description (e.g., Domain renewal)"
                  className="md:col-span-7 bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-300 placeholder:text-slate-400" />
                <input data-testid="expense-amount" type="number" min="0" step="0.01" value={newExpense.amount}
                  onChange={(e) => setNewExpense({ ...newExpense, amount: e.target.value })}
                  placeholder="$ Amount"
                  className="md:col-span-3 bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-300 placeholder:text-slate-400" />
                <button data-testid="expense-submit" type="submit"
                  className="md:col-span-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl font-semibold text-sm transition-colors py-3">
                  Log
                </button>
              </form>
            </div>

            <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
              <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
                <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                  <History className="w-4 h-4 text-slate-500" /> Ledger Entries
                </h3>
                <span className="text-xs text-slate-400">{expenses.length} total</span>
              </div>
              {expenses.length === 0 ? (
                <div data-testid="expenses-empty" className="px-6 py-12 text-center text-sm text-slate-400">
                  No entries yet. Log your first expense above.
                </div>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {expenses.map((e) => (
                    <li key={e.id} data-testid={`expense-row-${e.id}`}
                      className="px-6 py-4 flex items-center gap-4 hover:bg-slate-50 transition-colors">
                      <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center flex-shrink-0">
                        <Tag className="w-4 h-4 text-slate-500" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-semibold text-slate-800 truncate">{e.desc}</div>
                        <div className="text-xs text-slate-400">{e.date}</div>
                      </div>
                      <div className="text-sm font-bold text-slate-900">${parseFloat(e.amount).toFixed(2)}</div>
                      <button data-testid={`expense-delete-${e.id}`} onClick={() => removeExpense(e.id)}
                        className="text-slate-300 hover:text-red-500 transition-colors p-2">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}

        {/* ROADMAP / TIMELINE */}
        {activeTab === 'timeline' && ndaUnlocked && (
          <div data-testid="view-timeline" className="space-y-10">
            <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
              <div className="space-y-2">
                <h2 className="text-3xl font-bold text-slate-900 tracking-tight">Engagement Roadmap</h2>
                <p className="text-slate-500">Milestones across legal, technical and strategic vectors.</p>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-slate-400">Filter:</span>
                <select data-testid="roadmap-filter" value={filterProject}
                  onChange={(e) => setFilterProject(e.target.value)}
                  className="bg-white border border-slate-200 rounded-lg px-3 py-2 text-sm font-medium text-slate-700 outline-none focus:ring-2 focus:ring-blue-100">
                  <option>All</option>
                  <option>Legal</option>
                  <option>m8s rates</option>
                  <option>Account</option>
                  <option>ICT Infra</option>
                </select>
              </div>
            </div>

            <div className="relative pl-6 md:pl-8">
              <div className="absolute left-2 md:left-3 top-2 bottom-2 w-[2px] bg-slate-200" />
              <ul className="space-y-6">
                {filteredMilestones.map((m) => {
                  const cfg = m.status === 'completed'
                    ? { dot: 'bg-emerald-500', ring: 'ring-emerald-100', label: 'Completed', labelCls: 'bg-emerald-50 text-emerald-700 border-emerald-100' }
                    : m.status === 'pending'
                    ? { dot: 'bg-amber-500', ring: 'ring-amber-100', label: 'Pending', labelCls: 'bg-amber-50 text-amber-700 border-amber-100' }
                    : { dot: 'bg-slate-300', ring: 'ring-slate-100', label: 'Upcoming', labelCls: 'bg-slate-50 text-slate-600 border-slate-200' };
                  return (
                    <li key={m.id} data-testid={`milestone-${m.id}`} className="relative">
                      <span className={`absolute -left-[19px] md:-left-[26px] top-2 w-4 h-4 rounded-full ${cfg.dot} ring-4 ${cfg.ring}`} />
                      <div className="bg-white border border-slate-200 rounded-2xl p-5 hover:border-blue-200 hover:shadow-sm transition-all">
                        <div className="flex items-start justify-between gap-3 mb-2">
                          <h4 className="text-base font-bold text-slate-900">{m.title}</h4>
                          <span className={`text-xs font-semibold px-2.5 py-1 rounded-md border whitespace-nowrap ${cfg.labelCls}`}>{cfg.label}</span>
                        </div>
                        <p className="text-sm text-slate-500 mb-3">{m.desc}</p>
                        <div className="flex items-center gap-3 text-xs text-slate-400">
                          <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> {m.date}</span>
                          <span className="w-1 h-1 rounded-full bg-slate-300" />
                          <span>{m.project}</span>
                        </div>
                      </div>
                    </li>
                  );
                })}
                {filteredMilestones.length === 0 && (
                  <li data-testid="milestone-empty" className="text-sm text-slate-400 italic pl-2">
                    No milestones for this filter.
                  </li>
                )}
              </ul>
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default App;
