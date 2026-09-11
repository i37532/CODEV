#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_DIR="$REPO_DIR/.px4-python"
TOOLS_DIR="$REPO_DIR/.sitl-tools"
LOCAL_ROOT="$TOOLS_DIR/root"
LOCAL_JDK="$TOOLS_DIR/jdk"
LOCAL_ANT="$LOCAL_ROOT/usr/share/ant"

for command_name in git make python3 dpkg-deb apt-get; do
	if ! command -v "$command_name" >/dev/null 2>&1; then
		echo "错误：缺少命令 $command_name"
		exit 1
	fi
done

echo "[1/4] 修复仓库中被文件系统移除的脚本执行权限"
git -C "$REPO_DIR" ls-files -s | awk '$1 == "100755" {print $4}' |
	while IFS= read -r executable_file; do
		chmod u+x "$REPO_DIR/$executable_file"
	done

git -C "$REPO_DIR" submodule foreach --recursive --quiet \
	'git ls-files -s | awk '\''$1 == "100755" {print $4}'\'' | while IFS= read -r executable_file; do chmod u+x "$executable_file"; done'

echo "[2/4] 安装项目内 Python 构建依赖"
mkdir -p "$PYTHON_DIR"
python3 -m pip install --disable-pip-version-check --upgrade --target "$PYTHON_DIR" \
	'empy==3.3.4' \
	'jinja2<3.2' \
	'numpy<2' \
	packaging toml pyyaml kconfiglib jsonschema pyserial future pyros-genmsg

if [[ ! -x "$LOCAL_JDK/bin/java" || ! -x "$LOCAL_JDK/bin/javac" || ! -x "$LOCAL_ANT/bin/ant" ]]; then
	echo "[3/4] 安装项目内 OpenJDK 11 和 Ant（无需 sudo）"
	mkdir -p "$TOOLS_DIR/cache" "$LOCAL_ROOT" "$LOCAL_JDK"
	PACKAGE_DIR="$(mktemp -d "$TOOLS_DIR/cache/packages.XXXXXX")"

	(
		cd "$PACKAGE_DIR"
		apt-get download openjdk-11-jre-headless openjdk-11-jre openjdk-11-jdk-headless ant
	)

	find "$PACKAGE_DIR" -maxdepth 1 -type f -name '*.deb' -print0 |
		while IFS= read -r -d '' package_file; do
			dpkg-deb -x "$package_file" "$LOCAL_ROOT"
		done

	cp -a "$LOCAL_ROOT/usr/lib/jvm/java-11-openjdk-amd64/." "$LOCAL_JDK/"
else
	echo "[3/4] 项目内 OpenJDK 11 和 Ant 已就绪"
fi

export PYTHONPATH="$PYTHON_DIR${PYTHONPATH:+:$PYTHONPATH}"
export JAVA_HOME="$LOCAL_JDK"
export ANT_HOME="$LOCAL_ANT"
export PATH="$PYTHON_DIR/bin:$JAVA_HOME/bin:$ANT_HOME/bin:$PATH"

echo "[4/4] 编译 PX4 SITL 与 jMAVSim"
make -C "$REPO_DIR" px4_sitl_default
"$ANT_HOME/bin/ant" -f "$REPO_DIR/Tools/jMAVSim/build.xml" create_run_jar copy_res

echo
echo "完成。运行：$REPO_DIR/sitl/run.sh"
