import { useState, useEffect } from 'react';
import { Table, Button, Space, Tag, message, Modal, Typography, Card, Badge, Tooltip, Row, Col, Spin } from 'antd';
import {
    PlayCircleOutlined,
    PauseCircleOutlined,
    ReloadOutlined,
    SaveOutlined,
    DashboardOutlined,
    CloudUploadOutlined,
    PlusOutlined,
    DeleteOutlined,
    LockOutlined,
    CheckCircleOutlined,
    LoadingOutlined
} from '@ant-design/icons';
import { authAPI } from '../utils/authFetch';
import { API_BASE } from '../config';

const { Title, Text } = Typography;

function ContainerManager() {
    const [installedContainers, setInstalledContainers] = useState([]);
    const [optionalApps, setOptionalApps] = useState([]);
    const [loading, setLoading] = useState(true);
    const [actionInProgress, setActionInProgress] = useState(false);
    const [actionMessage, setActionMessage] = useState('');
    const [updateModal, setUpdateModal] = useState({ visible: false, container: null });
    const [uninstallModal, setUninstallModal] = useState({ visible: false, app: null });
    const [resourceSpec, setResourceSpec] = useState('2');

    const fetchContainers = async () => {
        try {
            const coreData = await authAPI.get('/versions/compare');
            const optionalData = await authAPI.get('/supos/apps/optional');

            setInstalledContainers(coreData.containers || []);
            setOptionalApps(optionalData.apps || []);
            setResourceSpec(optionalData.resource_spec || '2');
        } catch (err) {
            console.error('Fetch error:', err);
            message.error('Failed to fetch container status');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchContainers();
        const interval = setInterval(fetchContainers, 30000);
        return () => clearInterval(interval);
    }, []);

    const handleAction = async (containerId, action) => {
        setActionInProgress(true);
        setActionMessage(`${action === 'start' ? 'Starting' : 'Stopping'} container...`);

        try {
            await authAPI.post(`/supos/container/${containerId}/${action}`);
            message.success(`Container ${action}ed successfully`);
            setTimeout(fetchContainers, 1000);
        } catch (err) {
            console.error('Action error:', err);
            message.error(`Failed to ${action} container`);
        } finally {
            setActionInProgress(false);
            setActionMessage('');
        }
    };

    const handleUpdate = (containerName, currentVersion, recommendedVersion) => {
        setUpdateModal({
            visible: true,
            container: { containerName, currentVersion, recommendedVersion }
        });
    };

    const executeUpdate = async () => {
        const { containerName } = updateModal.container;
        setUpdateModal({ visible: false, container: null });

        setActionInProgress(true);
        setActionMessage(`Updating ${containerName}...`);

        setInstalledContainers(prev => prev.map(c =>
            c.name === containerName ? { ...c, status: 'updating' } : c
        ));

        try {
            const data = await authAPI.post(`/container/${containerName}/update`);

            if (data.success) {
                message.success(data.message);

                let attempts = 0;
                const pollInterval = setInterval(async () => {
                    attempts++;

                    try {
                        const freshData = await authAPI.get('/versions/compare');
                        const updatedContainer = freshData.containers.find(c => c.name === containerName);

                        if (updatedContainer && updatedContainer.status === 'running') {
                            clearInterval(pollInterval);
                            setInstalledContainers(freshData.containers);
                            setActionInProgress(false);
                            setActionMessage('');
                            message.success(`${containerName} updated successfully`);
                        } else if (attempts > 30) {
                            clearInterval(pollInterval);
                            setActionInProgress(false);
                            setActionMessage('');
                            fetchContainers();
                            message.warning('Update completed. Refresh to verify.');
                        }
                    } catch (err) {
                        console.error('Poll error:', err);
                    }
                }, 2000);
            } else {
                message.error(data.error || 'Update failed');
                fetchContainers();
                setActionInProgress(false);
                setActionMessage('');
            }
        } catch (err) {
            console.error('Update error:', err);
            message.error('Update failed');
            fetchContainers();
            setActionInProgress(false);
            setActionMessage('');
        }
    };

    const handleInstallApp = async (appId, appName) => {
        setActionInProgress(true);
        setActionMessage(`Installing ${appName}...`);

        try {
            const data = await authAPI.post(`/supos/apps/optional/${appId}/install`);

            if (data.success) {
                message.success(`${appName} installation started`);

                let attempts = 0;
                const pollInterval = setInterval(async () => {
                    attempts++;

                    try {
                        const optionalData = await authAPI.get('/supos/apps/optional');
                        const app = optionalData.apps.find(a => a.id === appId);

                        if (app && app.installed && app.status === 'running') {
                            clearInterval(pollInterval);
                            setOptionalApps(optionalData.apps);
                            setActionInProgress(false);
                            setActionMessage('');
                            fetchContainers();
                            message.success(`${appName} is now running`);
                        } else if (attempts > 30) {
                            clearInterval(pollInterval);
                            setActionInProgress(false);
                            setActionMessage('');
                            fetchContainers();
                            message.warning('Installation started. Refresh to verify.');
                        }
                    } catch (err) {
                        console.error('Poll error:', err);
                    }
                }, 2000);
            } else {
                message.error(data.error || 'Installation failed');
                setActionInProgress(false);
                setActionMessage('');
            }
        } catch (err) {
            console.error('Install error:', err);
            message.error(`Failed to install ${appName}`);
            setActionInProgress(false);
            setActionMessage('');
        }
    };

    const showUninstallModal = (app) => {
        setUninstallModal({ visible: true, app });
    };

    const executeUninstall = async () => {
        const app = uninstallModal.app;
        setUninstallModal({ visible: false, app: null });

        setActionInProgress(true);
        setActionMessage(`Uninstalling ${app.name}...`);

        try {
            const data = await authAPI.post(`/supos/apps/optional/${app.id}/uninstall`);

            if (data.success) {
                message.success(data.message);
                fetchContainers();
            } else {
                message.error(data.error || 'Uninstall failed');
            }
        } catch (err) {
            console.error('Uninstall error:', err);
            message.error(`Failed to uninstall: ${err.message}`);
        } finally {
            setActionInProgress(false);
            setActionMessage('');
        }
    };

    const handleBackup = () => {
        Modal.confirm({
            title: 'Create Backup',
            content: 'Backup all volumes and configuration?',
            onOk: async () => {
                setActionInProgress(true);
                setActionMessage('Creating backup...');

                try {
                    const data = await authAPI.post('/supos/backup');
                    if (data.success) {
                        message.success(`Backup created: ${data.backup_path}`);
                    }
                } catch (err) {
                    console.error('Backup error:', err);
                    message.error('Backup failed');
                } finally {
                    setActionInProgress(false);
                    setActionMessage('');
                }
            }
        });
    };

    const openSuposDashboard = async () => {
        try {
            const res = await fetch(`${API_BASE}/setup/status`);
            const data = await res.json();
            const { domain, port } = data.config.network;
            window.open(`http://${domain}:${port}/home`, '_blank');
        } catch {
            message.error('Failed to get dashboard URL');
        }
    };

    const installedColumns = [
        {
            title: 'Service',
            dataIndex: 'name',
            key: 'name',
            render: (name, record) => (
                <Space direction="vertical" size={0}>
                    <Text strong>{name}</Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>{record.image}</Text>
                </Space>
            )
        },
        {
            title: 'Status',
            dataIndex: 'status',
            key: 'status',
            render: (status) => (
                <Tag color={status === 'running' ? 'green' : status === 'exited' ? 'red' : 'orange'}>
                    {status.toUpperCase()}
                </Tag>
            )
        },
        {
            title: 'Version',
            key: 'version',
            render: (_, record) => (
                <Space direction="vertical" size={0}>
                    <Space>
                        <Text>Current:</Text>
                        <Tag color="blue">{record.current_version}</Tag>
                    </Space>
                    {record.recommended_version && (
                        <Space>
                            <Text>Latest:</Text>
                            <Tag color={record.update_available ? 'orange' : 'green'}>
                                {record.recommended_version}
                            </Tag>
                        </Space>
                    )}
                </Space>
            )
        },
        {
            title: 'Actions',
            key: 'actions',
            render: (_, record) => (
                <Space>
                    {record.status === 'running' ? (
                        <Button
                            size="small"
                            icon={<PauseCircleOutlined />}
                            onClick={() => handleAction(record.name, 'stop')}
                            disabled={actionInProgress}
                        >
                            Stop
                        </Button>
                    ) : (
                        <Button
                            size="small"
                            icon={<PlayCircleOutlined />}
                            onClick={() => handleAction(record.name, 'start')}
                            disabled={actionInProgress}
                        >
                            Start
                        </Button>
                    )}
                    {record.update_available && (
                        <Button
                            size="small"
                            type="primary"
                            icon={<CloudUploadOutlined />}
                            onClick={() => handleUpdate(record.name, record.current_version, record.recommended_version)}
                            disabled={actionInProgress}
                        >
                            Update
                        </Button>
                    )}
                </Space>
            )
        }
    ];

    const updatesAvailable = installedContainers.filter(c => c.update_available).length;
    const installedOptional = optionalApps.filter(a => a.installed).length;

    return (
        <>
            {actionInProgress && (
                <div style={{
                    position: 'fixed',
                    top: 0,
                    left: 0,
                    right: 0,
                    bottom: 0,
                    background: 'rgba(255, 255, 255, 0.9)',
                    zIndex: 9999,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 24
                }}>
                    <Spin size="large" indicator={<LoadingOutlined style={{ fontSize: 48 }} spin />} />
                    <Text style={{ fontSize: 16, color: '#1890ff', fontWeight: 500 }}>{actionMessage}</Text>
                </div>
            )}

            <div style={{ padding: 24 }}>
                <Space direction="vertical" style={{ width: '100%' }} size="large">
                    <Card>
                        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                            <div>
                                <Title level={3}>Container Management</Title>
                                <Space>
                                    {updatesAvailable > 0 && (
                                        <Badge count={updatesAvailable} style={{ backgroundColor: '#faad14' }}>
                                            <Text type="secondary">Updates Available</Text>
                                        </Badge>
                                    )}
                                    <Text type="secondary">
                                        • Resource Spec: {resourceSpec === '2' ? '8c16g' : '4c8g'}
                                    </Text>
                                    <Text type="secondary">
                                        • Optional Apps: {installedOptional}/5
                                    </Text>
                                </Space>
                            </div>
                            <Space>
                                <Button
                                    icon={<ReloadOutlined />}
                                    onClick={fetchContainers}
                                    loading={loading}
                                    disabled={actionInProgress}
                                >
                                    Refresh
                                </Button>
                                <Button
                                    icon={<SaveOutlined />}
                                    onClick={handleBackup}
                                    disabled={actionInProgress}
                                >
                                    Backup
                                </Button>
                                <Button
                                    type="primary"
                                    icon={<DashboardOutlined />}
                                    onClick={openSuposDashboard}
                                    disabled={actionInProgress}
                                >
                                    Open Dashboard
                                </Button>
                            </Space>
                        </Space>
                    </Card>

                    <Card>
                        <Title level={4}>Installed Services</Title>
                        <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
                            All running services (core platform + installed optional apps)
                        </Text>
                        <Table
                            columns={installedColumns}
                            dataSource={installedContainers}
                            rowKey="id"
                            loading={loading}
                            pagination={false}
                        />
                    </Card>

                    <Card>
                        <Title level={4}>Optional Apps</Title>
                        <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
                            Add or remove capabilities from your platform
                        </Text>
                        <Row gutter={[16, 16]}>
                            {optionalApps.map(app => {
                                const isInstalled = app.installed;
                                const isAvailable = app.available;

                                return (
                                    <Col xs={24} sm={12} lg={8} key={app.id}>
                                        <Card
                                            hoverable={isAvailable && !actionInProgress}
                                            style={{
                                                opacity: isAvailable ? 1 : 0.6,
                                                borderColor: isInstalled ? '#52c41a' : '#d9d9d9'
                                            }}
                                        >
                                            <Space direction="vertical" style={{ width: '100%' }} size="small">
                                                <Space>
                                                    <span style={{ fontSize: 32 }}>{app.icon}</span>
                                                    <div>
                                                        <Text strong style={{ fontSize: 16 }}>
                                                            {app.name}
                                                            {isInstalled && (
                                                                <CheckCircleOutlined
                                                                    style={{ marginLeft: 8, color: '#52c41a' }}
                                                                />
                                                            )}
                                                            {!isAvailable && (
                                                                <LockOutlined
                                                                    style={{ marginLeft: 8, color: '#bbb' }}
                                                                />
                                                            )}
                                                        </Text>
                                                        <br />
                                                        <Text type="secondary" style={{ fontSize: 12 }}>
                                                            {app.description}
                                                        </Text>
                                                    </div>
                                                </Space>

                                                {isInstalled && app.current_version && (
                                                    <div>
                                                        <Tag color="blue">{app.current_version}</Tag>
                                                        {app.status && (
                                                            <Tag color={app.status === 'running' ? 'green' : 'orange'}>
                                                                {app.status.toUpperCase()}
                                                            </Tag>
                                                        )}
                                                    </div>
                                                )}

                                                <div style={{ marginTop: 8 }}>
                                                    {!isAvailable ? (
                                                        <Tooltip title="Requires 8c16g (8 cores, 16GB RAM)">
                                                            <Button
                                                                size="small"
                                                                disabled
                                                                icon={<LockOutlined />}
                                                                block
                                                            >
                                                                Requires 8c16g
                                                            </Button>
                                                        </Tooltip>
                                                    ) : !isInstalled ? (
                                                        <Button
                                                            type="primary"
                                                            size="small"
                                                            icon={<PlusOutlined />}
                                                            onClick={() => handleInstallApp(app.id, app.name)}
                                                            disabled={actionInProgress}
                                                            block
                                                        >
                                                            Install
                                                        </Button>
                                                    ) : (
                                                        <Button
                                                            danger
                                                            size="small"
                                                            icon={<DeleteOutlined />}
                                                            onClick={() => showUninstallModal(app)}
                                                            disabled={actionInProgress}
                                                            block
                                                        >
                                                            Uninstall
                                                        </Button>
                                                    )}
                                                </div>
                                            </Space>
                                        </Card>
                                    </Col>
                                );
                            })}
                        </Row>
                    </Card>
                </Space>

                <Modal
                    title="Update Container"
                    open={updateModal.visible}
                    onOk={executeUpdate}
                    onCancel={() => setUpdateModal({ visible: false, container: null })}
                    okText="Update"
                    cancelText="Cancel"
                    okButtonProps={{ danger: true }}
                >
                    {updateModal.container && (
                        <div>
                            <p>Update <strong>{updateModal.container.containerName}</strong>?</p>
                            <p>Current: <Tag color="blue">{updateModal.container.currentVersion}</Tag></p>
                            <p>New: <Tag color="green">{updateModal.container.recommendedVersion}</Tag></p>
                            <p style={{ marginTop: 16, color: '#ff4d4f' }}>
                                ⚠️ Container will be stopped and recreated. Takes 1-2 minutes.
                            </p>
                        </div>
                    )}
                </Modal>

                <Modal
                    title="Uninstall Application"
                    open={uninstallModal.visible}
                    onOk={executeUninstall}
                    onCancel={() => setUninstallModal({ visible: false, app: null })}
                    okText="Uninstall"
                    cancelText="Cancel"
                    okButtonProps={{ danger: true }}
                >
                    {uninstallModal.app && (
                        <div>
                            <p>Uninstall <strong>{uninstallModal.app.name}</strong>?</p>
                            <p>This will stop and remove the service from your system.</p>
                            <p style={{ marginTop: 16, color: '#666' }}>
                                ℹ️ Data volumes will be preserved and restored on reinstall.
                            </p>
                        </div>
                    )}
                </Modal>
            </div>
        </>
    );
}

export default ContainerManager;
