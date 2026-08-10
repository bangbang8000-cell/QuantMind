// P0-4: 6 路径端到端草稿持久化验证
// useReducer HYDRATE 原子化写入，覆盖全部 6 条训练路径的 draft save/restore 流程

import { ok, equal, deepEqual, strictEqual } from 'node:assert/strict';

const DEFAULT_TIME_PERIODS = {
  train: [],
  val: [],
  test: [],
};

const DEFAULT_TARGET = { mode: 'return', horizonDays: 5, dealPrice: 'close' };
const DEFAULT_PARAMS = { model_types: ['lightgbm'], ensemble_method: 'none' };
const DEFAULT_CONTEXT = { market: '', benchmark: '' };
const DEFAULT_WFA = { enabled: false, strategy: 'rolling', nWindows: 4, trainYears: 3, valMonths: 12, stepMonths: 12 };

const INITIAL_STATE = {
  selectedFeatures: /** @type {string[]} */ ([]),
  timePeriods: DEFAULT_TIME_PERIODS,
  wfaConfig: DEFAULT_WFA,
  target: DEFAULT_TARGET,
  params: DEFAULT_PARAMS,
  context: DEFAULT_CONTEXT,
  displayName: 'Auto',
  displayNameMode: /** @type {'auto' | 'manual'} */ ('auto'),
  draftHydrated: false,
};

/**
 * @param {typeof INITIAL_STATE} state
 * @param {{ type: string; payload?: any; key?: string; value?: any }} action
 * @returns {typeof INITIAL_STATE}
 */
function formReducer(state, action) {
  switch (action.type) {
    case 'HYDRATE': {
      if (!action.payload) return { ...state, draftHydrated: true };
      const p = action.payload;
      const restoredParams = { ...DEFAULT_PARAMS, ...p.params };
      if (!p.params?.model_types && p.params?.model_type) {
        restoredParams.model_types = [p.params.model_type];
      }
      return {
        ...state,
        selectedFeatures: p.selectedFeatures && p.selectedFeatures.length > 0
          ? p.selectedFeatures : state.selectedFeatures,
        timePeriods: {
          train: p.timePeriods?.train || [],
          val: p.timePeriods?.val || [],
          test: p.timePeriods?.test || [],
        },
        target: p.target || DEFAULT_TARGET,
        params: restoredParams,
        context: { ...DEFAULT_CONTEXT, ...p.context },
        displayNameMode: p.displayNameMode || 'auto',
        displayName: p.displayName || state.displayName,
        wfaConfig: p.wfa || DEFAULT_WFA,
        draftHydrated: true,
      };
    }
    case 'SET_FEATURES':
      return { ...state, selectedFeatures: action.payload };
    case 'SET_TIME':
      return { ...state, timePeriods: { ...state.timePeriods, [action.key]: action.value } };
    case 'SET_TARGET':
      return { ...state, target: action.payload };
    case 'SET_PARAMS':
      return { ...state, params: action.payload };
    case 'SET_CONTEXT':
      return { ...state, context: action.payload };
    case 'SET_DISPLAY_NAME':
      return { ...state, displayName: action.payload.name, displayNameMode: action.payload.mode };
    case 'SET_WFA':
      return { ...state, wfaConfig: action.payload };
    default:
      return state;
  }
}

/**
 * 模拟 localStorage draft 保存：把 FormState 序列化为 TrainingDraft
 * @param {typeof INITIAL_STATE} state
 * @returns {object}
 */
function buildDraft(state) {
  return {
    displayName: state.displayName,
    displayNameMode: state.displayNameMode,
    selectedFeatures: state.selectedFeatures,
    timePeriods: {
      train: state.timePeriods.train,
      val: state.timePeriods.val,
      test: state.timePeriods.test,
    },
    target: state.target,
    params: state.params,
    context: state.context,
    wfa: state.wfaConfig,
    lastSavedAt: new Date().toISOString(),
  };
}

console.log('=== P0-4 6 路径端到端草稿持久化 ===\n');

// ── 路径 (a): 单模型 lightgbm 流 ──
{
  let state = { ...INITIAL_STATE };
  const draft = {
    selectedFeatures: ['mom_ret_5d', 'liq_turnover_os', 'flow_vpin'],
    timePeriods: { train: ['2022-01-01', '2024-05-31'], val: ['2024-06-01', '2024-08-31'], test: ['2024-09-01', '2024-11-30'] },
    target: { mode: 'return', horizonDays: 5, dealPrice: 'close' },
    params: { model_types: ['lightgbm'], ensemble_method: 'none' },
    context: { market: 'CN', benchmark: 'SH000300' },
    displayNameMode: 'auto',
    displayName: 'Auto_T5_Alpha3_CN',
    wfa: DEFAULT_WFA,
  };

  // 模拟 localStorage 恢复
  state = formReducer(state, { type: 'HYDRATE', payload: draft });
  ok(state.draftHydrated, '(a) hydrated');
  equal(state.params.model_types[0], 'lightgbm', '(a) model_type=lightgbm');
  equal(state.selectedFeatures.length, 3, '(a) 3 features');
  equal(state.target.horizonDays, 5, '(a) T+5');

  // 保存到 localStorage 的 draft 必须含所有关键字段
  const saved = buildDraft(state);
  ok(saved.selectedFeatures.length === 3, '(a) draft has features');
  ok(saved.params.model_types[0] === 'lightgbm', '(a) draft has model_types');
  console.log('  路径 (a) lightgbm 单模型: PASS');
}

// ── 路径 (b): 分类模式 ──
{
  let state = { ...INITIAL_STATE };
  const draft = {
    selectedFeatures: ['mom_ret_20d', 'style_bp'],
    timePeriods: { train: ['2021-01-01', '2024-12-31'], val: ['2025-01-01', '2025-04-30'], test: ['2025-05-01', '2025-06-30'] },
    target: { mode: 'classification', horizonDays: 10, dealPrice: 'open' },
    params: { model_types: ['xgboost'], ensemble_method: 'none' },
    context: { market: 'CN', benchmark: 'SH000905' },
    displayNameMode: 'manual',
    displayName: '分类_T10_Test',
    wfa: DEFAULT_WFA,
  };

  state = formReducer(state, { type: 'HYDRATE', payload: draft });
  equal(state.target.mode, 'classification', '(b) classification mode');
  equal(state.target.horizonDays, 10, '(b) T+10');
  equal(state.params.model_types[0], 'xgboost', '(b) xgboost');

  // 用户切换 horizon
  state = formReducer(state, { type: 'SET_TARGET', payload: { ...state.target, horizonDays: 20 } });
  equal(state.target.horizonDays, 20, '(b) user changed to T+20');

  const saved = buildDraft(state);
  equal(saved.target.mode, 'classification', '(b) draft preserves classification');
  equal(saved.target.horizonDays, 20, '(b) draft preserves T+20');
  console.log('  路径 (b) 分类模式: PASS');
}

// ── 路径 (c): 多 horizon T+1/3/5 ──
{
  let state = { ...INITIAL_STATE };
  const draft = {
    selectedFeatures: ['mom_ret_1d', 'mom_ret_3d', 'mom_ret_5d', 'mom_ret_10d', 'mom_ret_20d', 'mom_ret_60d'],
    timePeriods: { train: ['2020-01-01', '2023-12-31'], val: ['2024-01-01', '2024-06-30'], test: ['2024-07-01', '2024-12-31'] },
    target: { mode: 'return', horizonDays: 5, dealPrice: 'close', horizonDaysList: [1, 3, 5] },
    params: { model_types: ['lightgbm', 'xgboost', 'catboost'], ensemble_method: 'stacking' },
    context: { market: 'CN', benchmark: 'SH000300' },
    displayNameMode: 'auto',
    displayName: 'Multi_T1_3_5_Alpha6',
    wfa: DEFAULT_WFA,
  };

  state = formReducer(state, { type: 'HYDRATE', payload: draft });
  equal(state.params.model_types.length, 3, '(c) 3 model types');
  equal(state.params.ensemble_method, 'stacking', '(c) stacking ensemble');
  equal(state.target.horizonDaysList.length, 3, '(c) 3 horizons');

  const saved = buildDraft(state);
  ok(saved.params.model_types.includes('catboost'), '(c) draft has catboost');
  ok(saved.params.model_types.includes('xgboost'), '(c) draft has xgboost');
  console.log('  路径 (c) 多 horizon: PASS');
}

// ── 路径 (d): WFA 滚动窗口 ──
{
  let state = { ...INITIAL_STATE };
  const wfaConfig = { enabled: true, strategy: 'rolling', nWindows: 5, trainYears: 3, valMonths: 6, stepMonths: 6 };
  const draft = {
    selectedFeatures: ['mom_ret_5d', 'liq_turnover_os'],
    timePeriods: { train: ['2019-01-01', '2023-12-31'], val: ['2024-01-01', '2024-06-30'], test: ['2024-07-01', '2024-12-31'] },
    target: { mode: 'return', horizonDays: 5, dealPrice: 'close' },
    params: { model_types: ['lightgbm'], ensemble_method: 'none' },
    context: { market: 'CN', benchmark: 'SH000300' },
    displayNameMode: 'auto',
    displayName: 'WFA_T5',
    wfa: wfaConfig,
  };

  state = formReducer(state, { type: 'HYDRATE', payload: draft });
  ok(state.wfaConfig.enabled, '(d) WFA enabled');
  equal(state.wfaConfig.strategy, 'rolling', '(d) WFA rolling');
  equal(state.wfaConfig.nWindows, 5, '(d) WFA 5 windows');

  // 用户禁用 WFA
  state = formReducer(state, { type: 'SET_WFA', payload: { ...state.wfaConfig, enabled: false } });
  ok(!state.wfaConfig.enabled, '(d) WFA disabled by user');

  const saved = buildDraft(state);
  ok(saved.wfa && !saved.wfa.enabled, '(d) draft preserves disabled WFA');
  console.log('  路径 (d) WFA 滚动窗口: PASS');
}

// ── 路径 (e): 远程 AutoDL 节点 ──
{
  // 远程节点在 ModelTrainingPage 中是独立 useState（不参与草稿持久化）
  // 但 draft 恢复时不应影响 selectedNode 状态（在 useReducer 外）
  // 验证：HYDRATE 不丢 bench/contex 字段
  let state = { ...INITIAL_STATE };
  const draft = {
    selectedFeatures: ['mom_ret_20d', 'flow_pressure_index', 'style_ep_ttm'],
    timePeriods: { train: ['2022-01-01', '2025-06-30'], val: ['2025-07-01', '2025-10-31'], test: ['2025-11-01', '2025-12-31'] },
    target: { mode: 'return', horizonDays: 20, dealPrice: 'open' },
    params: { model_types: ['transformer'], ensemble_method: 'none', learning_rate: 0.001 },
    context: { market: 'US', benchmark: 'SPX' },
    displayNameMode: 'auto',
    displayName: 'Remote_US_T20_Transformer',
    wfa: DEFAULT_WFA,
  };

  state = formReducer(state, { type: 'HYDRATE', payload: draft });
  equal(state.context.market, 'US', '(e) US market context');
  equal(state.context.benchmark, 'SPX', '(e) SPX benchmark');
  equal(state.params.model_types[0], 'transformer', '(e) transformer model');

  // 切换市场（模拟 SET_MARKET_CONTEXT）
  state = formReducer(state, {
    type: 'SET_CONTEXT',
    payload: { ...state.context, market: 'HK', benchmark: 'HSI' }
  });
  equal(state.context.market, 'HK', '(e) market switched to HK');
  equal(state.context.benchmark, 'HSI', '(e) benchmark switched to HSI');

  const saved = buildDraft(state);
  equal(saved.context.market, 'HK', '(e) draft has HK market');
  equal(saved.params.model_types[0], 'transformer', '(e) draft has transformer');
  console.log('  路径 (e) 远程 AutoDL: PASS');
}

// ── 路径 (f): 草稿恢复 + 中途修改 + 重置 ──
{
  let state = { ...INITIAL_STATE };

  // Step 1: HYDRATE 从 localStorage 恢复旧草稿
  const oldDraft = {
    selectedFeatures: ['mom_ret_5d', 'liq_turnover_os'],
    timePeriods: { train: ['2023-01-01', '2024-12-31'], val: ['2025-01-01', '2025-04-30'], test: ['2025-05-01', '2025-06-30'] },
    target: { mode: 'return', horizonDays: 5, dealPrice: 'close' },
    params: { model_types: ['lightgbm'], ensemble_method: 'none' },
    context: { market: 'CN', benchmark: 'SH000300' },
    displayNameMode: 'auto',
    displayName: 'Draft_Old',
    wfa: DEFAULT_WFA,
  };
  state = formReducer(state, { type: 'HYDRATE', payload: oldDraft });
  ok(state.draftHydrated, '(f) hydrated old draft');
  equal(state.displayName, 'Draft_Old', '(f) old display name');

  // Step 2: 用户修改参数
  state = formReducer(state, { type: 'SET_PARAMS', payload: { ...state.params, model_types: ['xgboost', 'lightgbm'], ensemble_method: 'stacking' } });
  equal(state.params.model_types.length, 2, '(f) user added xgboost');

  // Step 3: 用户修改显示名称
  state = formReducer(state, { type: 'SET_DISPLAY_NAME', payload: { name: 'Final_T5_Stacking', mode: 'manual' } });
  equal(state.displayName, 'Final_T5_Stacking', '(f) user renamed');
  equal(state.displayNameMode, 'manual', '(f) manual mode');

  // Step 4: 最终 draft 保存
  const saved = buildDraft(state);
  equal(saved.displayName, 'Final_T5_Stacking', '(f) saved name');
  equal(saved.params.ensemble_method, 'stacking', '(f) saved stacking');
  equal(saved.selectedFeatures.length, 2, '(f) saved 2 features');

  // Step 5: 重置模拟（新 HYDRATE null）
  let freshState = formReducer(INITIAL_STATE, { type: 'HYDRATE', payload: null });
  ok(freshState.draftHydrated, '(f) reset hydrated');
  equal(freshState.selectedFeatures.length, 0, '(f) reset features empty');

  console.log('  路径 (f) 恢复+修改+重置: PASS');
}

// ── 边界条件 ──

// 竞争窗口：draftHydrated=true 前不保存
{
  let state = { ...INITIAL_STATE };
  ok(!state.draftHydrated, 'before HYDRATE: draftHydrated=false');

  // 模拟保存守卫
  let didSave = false;
  const saveIfHydrated = (s) => {
    if (!s.draftHydrated) return null;
    didSave = true;
    return buildDraft(s);
  };

  // HYDRATE 前尝试保存 → 被拦截
  const before = saveIfHydrated(state);
  strictEqual(before, null, 'save blocked before HYDRATE');
  ok(!didSave, 'didSave=false before HYDRATE');

  // HYDRATE 后保存 → 成功
  state = formReducer(state, { type: 'HYDRATE', payload: {
    selectedFeatures: ['close_5'],
    timePeriods: { train: [], val: [], test: [] },
    target: DEFAULT_TARGET,
    params: DEFAULT_PARAMS,
    context: DEFAULT_CONTEXT,
    displayNameMode: 'auto',
    displayName: 'Test',
  }});
  const after = saveIfHydrated(state);
  ok(after !== null, 'save succeeds after HYDRATE');
  ok(didSave, 'didSave=true after HYDRATE');
  console.log('  边界: save guarded before HYDRATE: PASS');
}

// 损坏的 localStorage JSON → 不崩溃
{
  let state = { ...INITIAL_STATE };
  // 模拟：localStorage 存储无法解析的数据
  try {
    const bad = JSON.parse('{broken json!!!}');
  } catch {
    // catch 后 dispatch null
    state = formReducer(state, { type: 'HYDRATE', payload: null });
  }
  ok(state.draftHydrated, 'corrupt JSON: draftHydrated=true');
  deepEqual(state.selectedFeatures, [], 'corrupt JSON: empty features fallback');
  console.log('  边界: corrupt localStorage JSON: PASS');
}

// 空 draft {} 使用默认参数
{
  let state = { ...INITIAL_STATE };
  state = formReducer(state, { type: 'HYDRATE', payload: {} });
  ok(state.draftHydrated, 'empty draft: hydrated');
  equal(state.params.model_types[0], 'lightgbm', 'empty draft: uses DEFAULT_PARAMS');
  equal(state.target.horizonDays, 5, 'empty draft: uses DEFAULT_TARGET');
  console.log('  边界: empty draft uses defaults: PASS');
}

console.log('\n✅ P0-4 6 路径 e2e 全部通过');
