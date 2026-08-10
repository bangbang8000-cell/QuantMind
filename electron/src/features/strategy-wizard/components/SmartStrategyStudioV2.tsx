import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { Layout, Steps, theme, Button, Space, Typography, Card, Divider, Breadcrumb, message, Alert, Modal, Tag } from 'antd';
import {
  BulbOutlined,
  ExperimentOutlined,
  SettingOutlined,
  RocketOutlined,
  LeftOutlined,
  RightOutlined,
  ArrowDownOutlined
} from '@ant-design/icons';
import { motion, AnimatePresence } from 'framer-motion';
import { NaturalTextInput } from './NaturalTextInput';
import { PoolPreview, type PoolPreviewHandle } from './PoolPreview';
import QlibParamsConfig from './QlibParamsConfig';
import QlibValidatorAndSave from './QlibValidatorAndSave';
import { useWizardV2Store } from '../store/wizardV2Store';
import { PAGE_LAYOUT } from '../../../config/pageLayout';
import { useAppSelector } from '../../../store';
import { selectCurrentMarket } from '../../../store/slices/uiSlice';
// 按需加载 wizardService 中的网络方法，避免静态/动态导入冲突
import { getWizardUserId } from '../utils/userId';
import { resolveRebalanceDays } from '../../../shared/qlib/rebalance';

const { Header, Content, Footer } = Layout;
const { Title, Text } = Typography;

const SmartStrategyStudioV2: React.FC = () => {
  const { token } = theme.useToken();
  const [currentStep, setCurrentStep] = useState(0);
  const [generating, setGenerating] = useState(false);
  const poolPreviewRef = useRef<PoolPreviewHandle>(null);
  const currentMarket = useAppSelector(selectCurrentMarket);

  // Use V2 store
  const {
    workingPool,
    savedPools,
    activePoolVersionId,
    conditions,
    qlibParams,
    generated,
    setGenerated,
    fetchWorkingPool,
    fetchSavedPools,
  } = useWizardV2Store();

  // Initial load
  useEffect(() => {
    fetchWorkingPool();
    fetchSavedPools();
  }, [fetchWorkingPool, fetchSavedPools]);

  const prev = useCallback(() => setCurrentStep(Math.max(currentStep - 1, 0)), [currentStep]);

  const next = useCallback(async () => {
    if (currentStep === 0) {
      // Step 1 -> Step 2: Already synced to backend via setWorkingPool
    }
    
    if (currentStep === 1) {
      // Step 2 -> Step 3: PoolPreview handles activation and saving
    }

    if (currentStep === 2) {
      // Step 3 -> Step 4: Generate Strategy
      if (!activePoolVersionId) {
        message.error('未激活股票池版本，请返回第二步确认');
        return;
      }

      setGenerating(true);
      try {
        const userId = getWizardUserId();
        const { generateQlib } = await import('../services/wizardService');
        const res = await generateQlib({
          user_id: userId,
          conditions: conditions || {},
          pool_file_key: activePoolVersionId,
          market: currentMarket,
          qlib_params: {
            ...qlibParams,
            market: currentMarket,
            rebalance_days: resolveRebalanceDays(qlibParams),
          },
        });

        if (!res?.success || !res?.code) {
          const reason = res?.error || '生成失败';
          message.error(`生成失败: ${reason}`);
          return;
        }

        setGenerated({ code: res.code });
        message.success('策略已生成');
      } catch (e: any) {
        const reason = e?.response?.data?.error || e?.message || '生成失败';
        message.error(`生成失败: ${reason}`);
        return;
      } finally {
        setGenerating(false);
      }
    }
    
    setCurrentStep(Math.min(currentStep + 1, 3));
  }, [currentStep, activePoolVersionId, conditions, qlibParams, setGenerated, currentMarket]);

  const steps = useMemo(() => [
    {
      title: '条件选股',
      icon: <BulbOutlined />,
      description: '自然语言或可视化构建',
    },
    {
      title: '确定股票池',
      icon: <ExperimentOutlined />,
      description: '预览与验证股票池',
    },
    {
      title: '策略参数',
      icon: <SettingOutlined />,
      description: 'Qlib专用参数（TopK / 调仓 / 风控）',
    },
    {
      title: '验证与保存',
      icon: <RocketOutlined />,
      description: 'Qlib验证并保存策略',
    }
  ], []);

  const renderStepContent = (stepIndex: number) => {
    switch (stepIndex) {
      case 0:
        return <NaturalTextInput onNext={next} />;
      case 1:
        return <PoolPreview ref={poolPreviewRef} onNext={next} onBack={prev} />;
      case 2:
        return <QlibParamsConfig onNext={next} onBack={prev} />;
      case 3:
        return <QlibValidatorAndSave onBack={prev} />;
      default:
        return null;
    }
  };

  const canProceed = (stepIndex: number) => {
    if (stepIndex === 0) {
      return (workingPool || []).length > 0;
    }
    if (stepIndex === 1) {
      return (workingPool || []).length > 0;
    }
    return true;
  };

  const nextDisabled = !canProceed(currentStep);

  return (
    <div className={PAGE_LAYOUT.outerClass}>
      <div className={PAGE_LAYOUT.frameClass}>
      <Modal
        title={
          <div style={{ textAlign: 'center', fontWeight: 800, letterSpacing: 0.3 }}>
            正在生成策略
          </div>
        }
        open={generating}
        closable={false}
        maskClosable={false}
        footer={null}
        centered
        styles={{
          header: { borderBottom: 'none', paddingBottom: 8 },
          body: { paddingTop: 6 }
        }}
      >
        <div
          style={{
            borderRadius: 12,
            padding: 16,
            background:
              'radial-gradient(1200px 220px at 50% -40px, rgba(59,130,246,0.18), transparent 55%),' +
              'linear-gradient(180deg, rgba(15,23,42,0.02), rgba(15,23,42,0.00))',
            border: '1px solid rgba(148,163,184,0.35)'
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'center', padding: '10px 0 14px' }}>
            <div
              style={{
                width: 220,
                height: 64,
                display: 'grid',
                gridTemplateColumns: 'repeat(7, 1fr)',
                columnGap: 8,
                alignItems: 'end'
              }}
              aria-label="策略生成进度动画"
            >
              {Array.from({ length: 7 }).map((_, i) => (
                <motion.div
                  key={i}
                  initial={{ scaleY: 0.35, opacity: 0.65 }}
                  animate={{
                    scaleY: [0.35, 1.05, 0.5, 0.95, 0.35],
                    opacity: [0.55, 1, 0.7, 1, 0.55]
                  }}
                  transition={{
                    duration: 1.35,
                    repeat: Infinity,
                    ease: 'easeInOut',
                    delay: i * 0.08
                  }}
                  style={{
                    height: 52,
                    transformOrigin: 'bottom',
                    borderRadius: 10,
                    background:
                      'linear-gradient(180deg, rgba(59,130,246,0.95), rgba(14,165,233,0.35))',
                    boxShadow: '0 10px 26px rgba(59,130,246,0.20)'
                  }}
                />
              ))}
            </div>
          </div>

          <Text style={{ color: '#475569', lineHeight: 1.7 }}>
            当前大模型正在根据您的需求生成策略，请稍等，整个过程可能需要 1-2 分钟。
            当策略生成并解析完毕，将自动关闭该窗口并进入下一步。
          </Text>
        </div>
      </Modal>
      <Layout
        style={{
          width: '100%',
          height: '100%',
          background: '#fff',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column'
        }}
      >
        {/* 顶部工具栏 - 对齐回测中心 */}
        <Header className={PAGE_LAYOUT.headerClass} style={{ height: PAGE_LAYOUT.headerHeight, padding: '0 24px', zIndex: 100 }}>
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-500 rounded-xl flex items-center justify-center shadow-md">
              <span className="text-white font-bold text-base">S</span>
            </div>
            <Title level={4} style={{ margin: 0, background: 'linear-gradient(45deg, #3b82f6, #8b5cf6)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', fontWeight: 700 }}>
              Smart Studio
            </Title>
          </div>
          <div style={{ flex: 1 }} />
          <Steps
            current={currentStep}
            size="small"
            style={{ width: 'min(500px, 100%)', flexShrink: 1, minWidth: 0 }}
            items={steps.map(s => ({ title: s.title }))}
          />
        </Header>

        <Layout style={{ flex: 1, overflow: 'hidden', minHeight: 0 }}>
          {/* 左侧导航已移除，改用顶部 Steps 导航，内容区占满全宽 */}

          <Layout style={{ background: '#f8fafc', padding: '0', display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0, minWidth: 0 }}>
            <div className="px-8 py-6 flex items-center justify-between bg-white border-b border-slate-50">
              <div className="flex flex-col">
                <Breadcrumb 
                  items={[
                    { title: <span className="text-slate-400">Strategy</span> },
                    { title: <span className="text-slate-600 font-medium">Smart Wizard</span> }
                  ]} 
                  style={{ marginBottom: 4, fontSize: 11 }}
                />
                <Title level={4} style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700, color: '#0f172a', letterSpacing: '-0.02em' }}>
                  {steps[currentStep].title}
                </Title>
              </div>
              <Space size="middle">
                <Button
                  onClick={prev}
                  disabled={currentStep === 0}
                  icon={<LeftOutlined />}
                  className="rounded-xl border-gray-200 hover:text-blue-500"
                >
                  上一步
                </Button>
                {currentStep < steps.length - 1 && (
                  <Button
                    type="primary"
                    onClick={() => {
                      if (currentStep === 1) {
                        // 第二步必须走 PoolPreview 的保存拦截逻辑，避免误跳第三步
                        poolPreviewRef.current?.triggerSaveAndNext();
                        return;
                      }
                      next();
                    }}
                    icon={currentStep === 2 ? <RocketOutlined /> : <RightOutlined />}
                    disabled={nextDisabled || generating}
                    loading={generating}
                    className="rounded-xl bg-gradient-to-r from-blue-500 to-purple-500 border-none shadow-md hover:shadow-lg transition-all"
                  >
                    {currentStep === 2 ? '立即生成策略' : '下一步'}
                  </Button>
                )}
              </Space>
            </div>

            {/* 核心卡片容器 - 严格对齐回测中心 */}
            <Content
              style={{
                padding: 0,
                overflowY: 'auto',
                position: 'relative',
                flex: 1,
                minHeight: 0
              }}
            >
                <div 
                  className="bg-white overflow-hidden"
                  style={{
                    margin: '12px 24px 24px 24px',
                    padding: 24,
                    borderRadius: '32px',
                    minHeight: 'calc(100% - 36px)',
                    display: 'flex',
                    flexDirection: 'column'
                  }}
                >
                  <div className="flex-1">
                    {renderStepContent(currentStep)}
                  </div>
                </div>
            </Content>

            {/* 状态栏 */}
            <Footer style={{
              display: 'flex',
              justifyContent: 'flex-end',
              alignItems: 'center',
              padding: '12px 24px',
              background: 'rgba(255, 255, 255, 0.8)',
              backdropFilter: 'blur(4px)',
              borderTop: '1px solid #e2e8f0',
              zIndex: 10
            }}>
              <Space split={<div className="inline-block h-4 w-px bg-gray-300 mx-2" />}>
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${generated?.code ? 'bg-green-500' : 'bg-amber-500 animate-pulse'}`} />
                  <Text type="secondary" className="text-xs">状态: {generated?.code ? '已生成' : '草稿'}</Text>
                </div>
                <Text type="secondary" className="text-xs">
                  股票池: <span className="font-medium text-gray-700">{Array.isArray(workingPool) ? `${workingPool.length} 只` : '未计算'}</span>
                </Text>
                <Text type="secondary" className="text-xs">
                  最后更新: <span className="font-mono">{new Date().toLocaleTimeString()}</span>
                </Text>
              </Space>
            </Footer>
          </Layout>
        </Layout>
      </Layout>
      <style>{`
        .no-scrollbar::-webkit-scrollbar {
          display: none;
        }
        .no-scrollbar {
          -ms-overflow-style: none;
          scrollbar-width: none;
        }
      `}</style>
      </div>
    </div>
  );
};

export default SmartStrategyStudioV2;
