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

IDCFクラウド コンテナには、nginx等の汎用Ingress Controllerではなく、
**独自のIngressClass**が用意されている(確認環境では `idcf-ilb`、
コントローラーは `idcfcloud.com/idcf-ingress`)。以下で確認する。

```bash
kubectl get ingressclass
```

表示された名前を、`k8s/ingress.yaml` の `ingressClassName` に設定する
(既定では `idcf-ilb` にしてあるが、環境によって名前が異なる可能性がある)。
この方式では、Ingress ControllerのServiceを探して手動でannotationを
付与するといった作業は不要で、正しいIngressClassを指定するだけで
ILBとの連携が行われる。

Ingressを経由せず、このアプリのServiceに直接ILBを紐づけたい場合は
`k8s/service-loadbalancer.example.yaml` を参照(ただしTLS終端が無いため、
Googleログインに必要なHTTPS化は別途対応が必要になる。cert-managerによる
TLS自動化を使いたい場合はIngress経由の方式を推奨する)。

### TLS証明書(手動登録)の設定

**このクラスタではcert-manager経由のLet's Encrypt(HTTP-01検証)は使えないことを
実機で確認済み。** cert-managerはHTTP-01検証のため、検証用パス
(`/.well-known/acme-challenge/<token>`)のみを持つ一時Ingressを自動生成するが、
IDCF独自の管理Webhook(`validate-idcf-ingress.idcfcloud.com`)は
「defaultBackendまたは`/`パスのルールが必要」としてこれを拒否するため、
証明書発行が構造的に失敗する(`kubectl describe challenge <name>` に
`admission webhook "validate-idcf-ingress.idcfcloud.com" denied ...
defaultBackend or setting the rule of specified "" path or "/" is required`
と表示される)。

そのため、既存の証明書ファイル(秘密鍵・証明書チェーン)を手動でSecretとして
登録する。`k8s/ingress.yaml` には `cert-manager.io/cluster-issuer` 注釈は
付けていない(付けるとcert-managerがこのSecretを上書き管理しようとして
干渉するため)。

```bash
kubectl -n pii-masking-shield create secret tls moya4-tls \
  --cert=path/to/fullchain.pem \
  --key=path/to/privkey.pem
```

証明書の有効期限が近づいたら、更新した証明書ファイルで同じコマンドを
再実行する(`--dry-run=client -o yaml | kubectl apply -f -` で上書き適用も可)。

```bash
kubectl -n pii-masking-shield get secret moya4-tls
```

(DNS-01検証に対応したDNSプロバイダを使っている場合は、上記の問題を回避できる
ため、`k8s/cluster-issuer.example.yaml` を参考にcert-managerでの自動化も
検討できる。ただしこのクラスタでの動作確認はしていない)。

### SSLポリシー(IDCFクラウド固有)の設定

IDCFクラウドのIngressで`tls:`ブロックを使う場合、事前にIDCFクラウド コンソール
でSSLポリシーを発行し、そのIDを `k8s/ingress.yaml` の
`ilb.idcfcloud.com/sslpolicy-id` annotationに設定する必要がある
(実機で確認済み。`k8s/ingress.yaml` には設定済みのSSLポリシーIDが入っている)。
これが無い、または値が誤っていると、Ingressの`ADDRESS`が割り当てられず
LBの生成に失敗する。

```bash
kubectl -n pii-masking-shield describe ingress moya4
# Warning Error ... generateLB failed: TLS SecretName "moya4-tls" exists,
# but "ilb.idcfcloud.com/sslpolicy-id" annotation is not found
# と表示される場合、上記annotationが未設定または値が誤っている。
```

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
| Ingress経由でアクセスできない | `ingressClassName` が実際のクラスタの名前と違う | `kubectl get ingressclass`(上記1章参照) |
| HTTPSでアクセスできない・証明書エラー | `moya4-tls` Secretが未作成、または証明書ファイルが誤っている(このクラスタではcert-manager自動発行は使えない。上記「TLS証明書(手動登録)の設定」参照) | `kubectl -n pii-masking-shield get secret moya4-tls` |
| Challengeが`pending`のまま・`admission webhook "validate-idcf-ingress.idcfcloud.com" denied ... defaultBackend or ... path or "/" is required` | cert-managerのHTTP-01検証用一時IngressがIDCFの管理Webhookに拒否されている(このクラスタでは構造的に非対応。手動証明書登録に切り替える) | `kubectl -n pii-masking-shield describe challenge <name>` |
| `kubectl apply`が`admission webhook "validate-idcf-ingress.idcfcloud.com" denied`で失敗 | IngressのpathTypeが`ImplementationSpecific`以外になっている(IDCF独自の制約。`k8s/ingress.yaml`は対応済み) | `kubectl -n pii-masking-shield get ingress moya4 -o yaml \| Select-String pathType` |
| Ingressの`ADDRESS`が割り当てられない・`generateLB failed`エラー | `ilb.idcfcloud.com/sslpolicy-id` annotationが未設定、またはSSLポリシーIDが誤っている | `kubectl -n pii-masking-shield describe ingress moya4` |
| Googleログインでエラーになる | Ingressのホスト名とGoogle Cloud ConsoleのリダイレクトURIが不一致 | `kubectl -n pii-masking-shield get ingress moya4 -o yaml` |
