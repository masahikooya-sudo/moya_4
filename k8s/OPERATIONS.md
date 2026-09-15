# 運用手順(IDCFクラウド コンテナ)

IDCFクラウド コンテナ(SUSE Rancher/RKE2ベースのマネージドKubernetes)上で、
本アプリを起動・停止・更新・削除するための手順をまとめる。
マニフェスト自体の内容や初回セットアップの前提条件は `../README.md` の
「Kubernetes(IDCFクラウド等)」セクションを参照(イメージのビルド・プッシュ、
Secretの作成、ドメイン設定など)。

## 0. 前提: kubectlの接続確認

IDCFクラウド コンテナのコンソールで対象クラスターのダッシュボードを開き、
上部メニューの「KubeConfigをダウンロード」からkubeconfigファイルを取得する。
ダウンロードされるkubeconfigには2種類のcontextが含まれる。

- コンソールを **経由して** 接続するcontext(社内ネットワーク等を問わず使える)
- コンソールを **経由せず** 直接クラスターへ接続するcontext(低遅延だが、
  クラスターへの直接到達性が必要)

どちらを使うかは `kubectl config get-contexts` / `kubectl config use-context <name>`
で切り替えられる。まずは以下で疎通を確認する。

```bash
export KUBECONFIG=/path/to/downloaded-kubeconfig.yaml
kubectl get nodes
```

## 1. 起動(初回デプロイ)

`README.md` の手順1〜5(イメージのビルド・プッシュ、レジストリSecret作成、
`kustomization.yaml` の書き換え、Google認証情報Secretの作成、ドメイン設定)を
済ませたうえで、以下を実行する。

```bash
kubectl apply -k k8s/
kubectl -n pii-masking-shield rollout status deployment/moya4
```

`rollout status` が `deployment "moya4" successfully rolled out` と表示されれば
起動完了。Presidio/spaCyモデルの読み込みに数十秒かかることがあるが、
`startupProbe` がこれを待つよう設定済みなので、Podが `Running` になった後
自動的に受付可能な状態へ遷移する。

```bash
kubectl -n pii-masking-shield get pods
kubectl -n pii-masking-shield logs -f deployment/moya4
```

ドメイン・Ingressの設定が完了していれば `https://<ドメイン>/` でアクセスできる。
未設定の段階で先に動作だけ確認したい場合はポートフォワードを使う。

```bash
kubectl -n pii-masking-shield port-forward svc/moya4 8000:80
```

### ILB(Infinite LB)との連携について

ILBの申し込みが完了していても、**Kubernetes側での紐付けは別途必要な場合がある**。
以下で確認する。

```bash
kubectl get svc -A | grep -i ingress
```

IDCFクラウド コンテナ(RKE2ベース)にはnginx Ingress Controllerが標準で
同梱されていることが多く、上記コマンドでその `Service`(通常
`kube-system` 名前空間、`type: LoadBalancer`)が見つかるはずである。
この`Service`に `EXTERNAL-IP` が付与されていて、それがILBのIPと一致していれば
既に連携済み。付与されていない場合は、その`Service`に以下のannotationを
追加する(IDCFクラウドのコンソール操作で自動付与されることもあるため、
まず現状を確認してから対応すること)。

```yaml
metadata:
  annotations:
    loadbalancer.idcfcloud.com/loadbalancer-class: "ilb"
```

Ingress Controllerを経由せず、このアプリのServiceを直接ILBで公開したい場合は
`k8s/service-loadbalancer.example.yaml` を参照(ただしTLS終端が無いため、
Googleログインに必要なHTTPS化は別途対応が必要になる。cert-managerによる
TLS自動化を使いたい場合はIngress経由の方式を推奨する)。

## 2. 停止(一時停止・コスト抑制)

**設定やデータ(PVC/ConfigMap/Secret/Service/Ingress)は残したまま、
Podだけを止めたい場合:**

```bash
kubectl -n pii-masking-shield scale deployment/moya4 --replicas=0
```

再開する場合は元に戻すだけでよい(イメージやSecretの再作成は不要)。

```bash
kubectl -n pii-masking-shield scale deployment/moya4 --replicas=1
kubectl -n pii-masking-shield rollout status deployment/moya4
```

> **注意**: この操作はコンテナ(Pod)の計算リソースの課金を止めるだけで、
> IDCFクラウド側で申し込んだ **ILB自体の課金は止まらない**。ILBの利用を
> 一時的に止めたい場合は、IDCFクラウドのコンソールから別途対応する必要がある。

## 3. 更新(コード変更・設定変更の反映)

### アプリのコードを変更した場合

```bash
# 1. 新しいイメージをビルド・プッシュ(タグを変えることを推奨。
#    :latest の使い回しだとロールバック時にどのコードか分からなくなる)
docker build -t <REGISTRY>/moya4:2026-09-15 .
docker push <REGISTRY>/moya4:2026-09-15

# 2. kustomization.yaml の newTag を書き換える
#    (images: - name: moya4 / newTag: "2026-09-15")

# 3. 適用
kubectl apply -k k8s/
kubectl -n pii-masking-shield rollout status deployment/moya4
```

動作に問題があれば直前のバージョンに戻せる。

```bash
kubectl -n pii-masking-shield rollout undo deployment/moya4
```

### 環境変数(ConfigMap/Secret)だけを変更した場合

`k8s/configmap.yaml` を編集した場合や、Secretの値を
`kubectl create secret ... --dry-run=client -o yaml | kubectl apply -f -`
等で更新した場合、**ConfigMap/Secretの変更はPodへ自動反映されない**。
変更を反映するには、Podを再作成させる必要がある。

```bash
kubectl apply -k k8s/          # ConfigMapの内容を更新
kubectl -n pii-masking-shield rollout restart deployment/moya4
kubectl -n pii-masking-shield rollout status deployment/moya4
```

### ドメイン・TLS設定だけを変更した場合

`k8s/ingress.yaml` を編集して `kubectl apply -k k8s/` を実行するだけでよい
(Podの再起動は不要)。

## 4. 削除(後始末)

**このアプリに関するKubernetesリソースを全て削除する場合:**

```bash
kubectl delete -k k8s/
```

`k8s/namespace.yaml` がリソース一覧に含まれるため、この1コマンドで
Namespace(`pii-masking-shield`)ごと削除され、`kubectl create secret` で
別途作成した `moya4-secrets` / `moya4-registry-cred` を含め、この名前空間内の
リソースが全て一掃される。

> **⚠️ 重要**: Namespaceの削除により、監査ログを保存していたPVC
> (`moya4-logs`)も削除され、**中のログは復元できなくなる**。
> 削除前にログを保管しておきたい場合は、事前に取り出しておくこと。
>
> ```bash
> kubectl -n pii-masking-shield cp \
>   $(kubectl -n pii-masking-shield get pod -l app=moya4 -o jsonpath='{.items[0].metadata.name}'):/app/logs \
>   ./moya4-logs-backup
> ```

削除後、以下はKubernetesの外側(IDCFクラウド側)の後始末になるため、
必要に応じて別途対応する。

- **ILBの契約解除**: このアプリ用に申し込んだILBをもう使わない場合、
  IDCFクラウドのコンソールから解除しないと課金が続く。他のアプリと共用
  している場合は解除しないこと。
- **コンテナレジストリ上のイメージ**: 不要になった場合は
  `docker rmi` や、レジストリ側の管理画面/APIで削除する。
- **クラスター自体**: 他に稼働中のアプリが無く、クラスターごと不要になった
  場合は、IDCFクラウドのコンソールからクラスターの削除を行う
  (このアプリのマニフェストの範囲外)。

## トラブルシューティング早見表

| 症状 | 主な原因 | 確認コマンド |
|---|---|---|
| Podが`Pending`のまま | PVCがbindできていない(StorageClass不一致) | `kubectl -n pii-masking-shield get pvc` / `kubectl get storageclass` |
| `ImagePullBackOff` | レジストリ認証Secット未設定・誤り、またはレジストリがHTTPS化されていない | `kubectl -n pii-masking-shield describe pod <pod名>` |
| Podは`Running`だが`Ready`にならない | 起動直後でspaCyモデル読み込み中(`startupProbe`待ち、数十秒かかることがある) | `kubectl -n pii-masking-shield logs deployment/moya4` |
| Ingress経由でアクセスできない | ILBがIngress ControllerのServiceに紐づいていない | `kubectl get svc -A \| grep -i ingress`(上記1章参照) |
| Googleログインでエラーになる | Ingressのホスト名とGoogle Cloud ConsoleのリダイレクトURIが不一致 | `kubectl -n pii-masking-shield get ingress moya4 -o yaml` |
