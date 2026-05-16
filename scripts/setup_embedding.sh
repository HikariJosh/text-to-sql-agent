#!/bin/bash
# 下载 BGE-large-zh-v1.5 embedding 模型
# 模型文件较大（~1.2GB），不放在 git 仓库中，需要单独下载

set -e

MODEL_DIR="docker/embedding/bge-large-zh-v1.5"

if [ -d "$MODEL_DIR" ] && [ -f "$MODEL_DIR/pytorch_model.bin" ]; then
    echo "模型已存在，跳过下载"
    exit 0
fi

echo "正在下载 BGE-large-zh-v1.5 模型..."
mkdir -p "$MODEL_DIR"

# 使用 huggingface-hub 下载（需要 pip install huggingface-hub）
python3 -c "
from huggingface_hub import snapshot_download
snapshot_download(
    'BAAI/bge-large-zh-v1.5',
    local_dir='$MODEL_DIR',
    local_dir_use_symlinks=False,
)
print('模型下载完成')
"

echo "模型已下载到 $MODEL_DIR"
