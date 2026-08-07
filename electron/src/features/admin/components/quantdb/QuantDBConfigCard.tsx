import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Descriptions, Input, Space, Tag, Typography, message } from 'antd';
import { ApiOutlined, KeyOutlined, SaveOutlined } from '@ant-design/icons';
import { dataPlatformService, QuantDBConfig } from '../../services/dataPlatformService';
import { describeError } from './utils';

const { Text } = Typography;

interface QuantDBConfigCardProps {
    /** 保存成功后通知外层刷新 SDK 状态 */
    onSaved: () => void;
}

export function QuantDBConfigCard({ onSaved }: QuantDBConfigCardProps) {
    const [config, setConfig] = useState<QuantDBConfig | null>(null);
    const [apiKey, setApiKey] = useState('');
    const [saving, setSaving] = useState(false);
    const [verifyError, setVerifyError] = useState<string | null>(null);

    const loadConfig = useCallback(async () => {
        try {
            setConfig(await dataPlatformService.getQuantDBConfig());
        } catch (error: unknown) {
            message.error(`获取 QuantDB 配置失败: ${describeError(error)}`);
        }
    }, []);

    useEffect(() => {
        loadConfig();
    }, [loadConfig]);

    const handleSave = async () => {
        const trimmed = apiKey.trim();
        if (trimmed.length < 8) {
            message.warning('请输入完整的 API Key');
            return;
        }
        setSaving(true);
        setVerifyError(null);
        try {
            const result = await dataPlatformService.saveQuantDBConfig(trimmed);
            if (result.verified) {
                message.success('API Key 已保存并验证通过');
            } else {
                setVerifyError(result.error ?? '未知原因');
                message.warning('API Key 已保存，但连接验证失败');
            }
            setApiKey('');
            await loadConfig();
            onSaved();
        } catch (error: unknown) {
            message.error(`保存失败: ${describeError(error)}`);
        } finally {
            setSaving(false);
        }
    };

    return (
        <Card size="small" title={<Space><KeyOutlined />API Key 配置</Space>}>
            <Space direction="vertical" className="w-full" size="middle">
                <Space wrap>
                    <Input.Password
                        placeholder="粘贴 QuantDB API Key"
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                        onPressEnter={handleSave}
                        style={{ width: 340 }}
                        autoComplete="off"
                    />
                    <Button
                        type="primary"
                        icon={<SaveOutlined />}
                        onClick={handleSave}
                        loading={saving}
                    >
                        保存并验证
                    </Button>
                    <Tag
                        color={config?.api_key_configured ? 'green' : 'red'}
                        icon={<ApiOutlined />}
                    >
                        {config?.api_key_configured
                            ? `已配置 ${config.api_key_masked}`
                            : '未配置'}
                    </Tag>
                </Space>

                {verifyError && (
                    <Alert
                        type="warning"
                        showIcon
                        message="Key 已写入，但调用 QuantDB 失败"
                        description={verifyError}
                        closable
                        onClose={() => setVerifyError(null)}
                    />
                )}

                {config && (
                    <Descriptions size="small" column={1}>
                        <Descriptions.Item label="本地数据目录">
                            <Text code>{config.data_dir}</Text>
                        </Descriptions.Item>
                        <Descriptions.Item label="密钥文件">
                            <Text code>{config.runtime_env_file}</Text>
                        </Descriptions.Item>
                    </Descriptions>
                )}

                <Text type="secondary" className="text-xs">
                    Key 写入密钥文件后立即生效，服务重启仍有效；页面只显示脱敏值，不回传明文。
                    若环境变量 QUANTDB_API_KEY 已设置非空值，则环境变量优先。
                </Text>
            </Space>
        </Card>
    );
}

export default QuantDBConfigCard;
