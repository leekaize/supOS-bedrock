import { useState, useEffect } from 'react';
import {
    Modal, Table, Button, Space, message, Tag, Tooltip, Typography, Spin, Input, Form
} from 'antd';
import {
    CloudUploadOutlined, ReloadOutlined, DeleteOutlined,
    WarningOutlined, HistoryOutlined, FolderOutlined, EditOutlined,
    CheckOutlined, CloseOutlined
} from '@ant-design/icons';
import { authAPI } from '../utils/authFetch';
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';
import relativeTime from 'dayjs/plugin/relativeTime';

dayjs.extend(utc);
dayjs.extend(timezone);
dayjs.extend(relativeTime);

const { Text } = Typography;

function BackupRestoreModal({ visible, onCancel, onRestore }) {
    const [backups, setBackups] = useState([]);
    const [loading, setLoading] = useState(false);
    const [creating, setCreating] = useState(false);
    const [backupDir, setBackupDir] = useState('/volumes/supos/backups');
    const [editDirModal, setEditDirModal] = useState(false);
    const [confirmAction, setConfirmAction] = useState(null); // {action: 'restore'|'delete', name: 'backup_123'}
    const [form] = Form.useForm();

    useEffect(() => {
        if (visible) {
            fetchBackups();
            fetchBackupConfig();
        }
    }, [visible]);

    const fetchBackups = async () => {
        setLoading(true);
        try {
            const data = await authAPI.get('/backup/list');
            setBackups(data.backups || []);
        } catch (err) {
            console.error('Fetch error:', err);
            message.error('Failed to load backups');
        } finally {
            setLoading(false);
        }
    };

    const fetchBackupConfig = async () => {
        try {
            const data = await authAPI.get('/backup/config');
            setBackupDir(data.backup_path || '/volumes/supos/backups');
        } catch (err) {
            console.error('Config fetch error:', err);
        }
    };

    const handleCreateBackup = async () => {
        setCreating(true);
        message.loading({ content: 'Creating backup...', key: 'backup', duration: 0 });

        try {
            const result = await authAPI.post('/backup/create', {});
            message.success({
                content: `Backup created: ${result.archive_name}`,
                key: 'backup',
                duration: 3
            });
            fetchBackups();
        } catch (err) {
            console.error('Backup error:', err);
            message.error({
                content: err.message || 'Backup failed',
                key: 'backup'
            });
        } finally {
            setCreating(false);
        }
    };

    const handleConfirmRestore = () => {
        const archiveName = confirmAction.name;
        setConfirmAction(null);
        onRestore(archiveName);
    };

    const handleConfirmDelete = async () => {
        const archiveName = confirmAction.name;
        setConfirmAction(null);

        try {
            message.loading({ content: 'Deleting backup...', key: 'delete' });
            await authAPI.post('/backup/delete', { archive_name: archiveName });
            message.success({ content: 'Backup deleted', key: 'delete' });
            fetchBackups();
        } catch (err) {
            console.error('Delete error:', err);
            message.error({ content: 'Delete failed', key: 'delete' });
        }
    };

    const handleChangeDirectory = async (values) => {
        try {
            await authAPI.post('/backup/config', { backup_path: values.backup_path });
            setBackupDir(values.backup_path);
            message.success('Backup directory updated');
            setEditDirModal(false);
            fetchBackups();
        } catch (err) {
            message.error('Failed to update directory');
        }
    };

    const formatBytes = (bytes) => {
        if (!bytes || bytes === 0) return '0 B';
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${sizes[i]}`;
    };

    const columns = [
        {
            title: 'Backup Name',
            dataIndex: 'name',
            key: 'name',
            width: 220,
            render: (name) => <Text code style={{ fontSize: 12 }}>{name}</Text>
        },
        {
            title: 'Created',
            dataIndex: 'timestamp',
            key: 'timestamp',
            width: 150,
            render: (timestamp) => {
                const localTime = dayjs.utc(timestamp).local();
                return (
                    <Tooltip title={localTime.format('YYYY-MM-DD HH:mm:ss')}>
                        <Text>{localTime.fromNow()}</Text>
                    </Tooltip>
                );
            },
            sorter: (a, b) => new Date(a.timestamp) - new Date(b.timestamp),
            defaultSortOrder: 'descend'
        },
        {
            title: 'Size',
            key: 'size',
            width: 150,
            render: (_, record) => {
                const compressed = record.stats?.compressed_size || 0;
                const original = record.stats?.original_size || 0;
                const dedup = record.stats?.deduplicated_size || 0;
                const savings = original > 0 ? ((1 - compressed / original) * 100).toFixed(1) : 0;

                return (
                    <Tooltip title={
                        <div>
                            <div>Original: {formatBytes(original)}</div>
                            <div>Compressed: {formatBytes(compressed)}</div>
                            <div>After dedup: {formatBytes(dedup)}</div>
                            <div style={{ marginTop: 4, fontSize: 11, opacity: 0.8 }}>
                                Dedup size is small because data exists in previous backups
                            </div>
                        </div>
                    }>
                        <Space>
                            <Text>{formatBytes(compressed)}</Text>
                            {savings > 0 && (
                                <Tag color="green" style={{ fontSize: 11 }}>
                                    {savings}% saved
                                </Tag>
                            )}
                        </Space>
                    </Tooltip>
                );
            }
        },
        {
            title: 'Actions',
            key: 'actions',
            width: 180,
            render: (_, record) => {
                // Show confirmation buttons if this row is being confirmed
                if (confirmAction?.name === record.name) {
                    if (confirmAction.action === 'restore') {
                        return (
                            <Space direction="vertical" size="small" style={{ width: '100%' }}>
                                <Text type="danger" strong style={{ fontSize: 12 }}>
                                    ⚠️ Confirm Restore?
                                </Text>
                                <Space size="small">
                                    <Button
                                        type="primary"
                                        danger
                                        size="small"
                                        icon={<CheckOutlined />}
                                        onClick={handleConfirmRestore}
                                    >
                                        Yes
                                    </Button>
                                    <Button
                                        size="small"
                                        icon={<CloseOutlined />}
                                        onClick={() => setConfirmAction(null)}
                                    >
                                        No
                                    </Button>
                                </Space>
                            </Space>
                        );
                    } else if (confirmAction.action === 'delete') {
                        return (
                            <Space direction="vertical" size="small" style={{ width: '100%' }}>
                                <Text type="danger" strong style={{ fontSize: 12 }}>
                                    ⚠️ Confirm Delete?
                                </Text>
                                <Space size="small">
                                    <Button
                                        type="primary"
                                        danger
                                        size="small"
                                        icon={<CheckOutlined />}
                                        onClick={handleConfirmDelete}
                                    >
                                        Yes
                                    </Button>
                                    <Button
                                        size="small"
                                        icon={<CloseOutlined />}
                                        onClick={() => setConfirmAction(null)}
                                    >
                                        No
                                    </Button>
                                </Space>
                            </Space>
                        );
                    }
                }

                // Default buttons
                return (
                    <Space size="small">
                        <Button
                            type="primary"
                            size="small"
                            icon={<HistoryOutlined />}
                            onClick={() => setConfirmAction({ action: 'restore', name: record.name })}
                        >
                            Restore
                        </Button>
                        <Button
                            danger
                            size="small"
                            icon={<DeleteOutlined />}
                            onClick={() => setConfirmAction({ action: 'delete', name: record.name })}
                        />
                    </Space>
                );
            }
        }
    ];

    return (
        <>
            <Modal
                title="Backup & Restore"
                open={visible}
                onCancel={onCancel}
                width={900}
                footer={[
                    <Button key="refresh" icon={<ReloadOutlined />} onClick={fetchBackups}>
                        Refresh
                    </Button>,
                    <Button
                        key="create"
                        type="primary"
                        icon={<CloudUploadOutlined />}
                        onClick={handleCreateBackup}
                        loading={creating}
                    >
                        Create Backup
                    </Button>,
                    <Button key="close" onClick={onCancel}>
                        Close
                    </Button>
                ]}
            >
                <div style={{ marginBottom: 16, padding: 12, background: '#f5f5f5', borderRadius: 4 }}>
                    <Space>
                        <FolderOutlined />
                        <Text strong>Backup Directory:</Text>
                        <Text code>{backupDir}</Text>
                        <Button
                            size="small"
                            icon={<EditOutlined />}
                            onClick={() => {
                                form.setFieldsValue({ backup_path: backupDir });
                                setEditDirModal(true);
                            }}
                        >
                            Change
                        </Button>
                    </Space>
                </div>

                {loading ? (
                    <div style={{ textAlign: 'center', padding: 50 }}>
                        <Spin size="large" />
                    </div>
                ) : backups.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: 50 }}>
                        <Text type="secondary">No backups found. Create your first backup.</Text>
                    </div>
                ) : (
                    <Table
                        columns={columns}
                        dataSource={backups}
                        rowKey="id"
                        pagination={{ pageSize: 10, showSizeChanger: false }}
                        size="small"
                    />
                )}
            </Modal>

            <Modal
                title="Change Backup Directory"
                open={editDirModal}
                onCancel={() => setEditDirModal(false)}
                footer={null}
                width={500}
            >
                <Form form={form} onFinish={handleChangeDirectory} layout="vertical">
                    <Form.Item
                        name="backup_path"
                        label="Backup Directory Path"
                        rules={[{ required: true, message: 'Path is required' }]}
                        extra="Must be accessible from the container. Ensure path exists and has write permissions."
                    >
                        <Input placeholder="/volumes/supos/backups" />
                    </Form.Item>
                    <Form.Item>
                        <Space>
                            <Button type="primary" htmlType="submit">
                                Save
                            </Button>
                            <Button onClick={() => setEditDirModal(false)}>
                                Cancel
                            </Button>
                        </Space>
                    </Form.Item>
                </Form>
            </Modal>
        </>
    );
}

export default BackupRestoreModal;
