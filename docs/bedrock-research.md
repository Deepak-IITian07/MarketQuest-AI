# Amazon Bedrock integration research (MarketQuest AI)

**Status: the integration is implemented and covered by mocked tests. No live
AWS call has been made, and no credential has been read, printed or created.**
What was built is in [§10](#10-what-was-implemented); the account-side setup
that is still outstanding is in [§8](#8-what-the-operator-must-do-first).

Scope: how a Python FastAPI backend would call a **generative** model on Amazon
Bedrock to turn market-analysis results into a written explanation.

**This document deliberately does NOT cover tool selection.** In MarketQuest AI
the tool-selection decision belongs to Strands Decider 2B (see
`docs/decision-pattern.md`). Bedrock's job is the *other* half: it receives
numbers that have already been computed and writes the human-readable
explanation. See [§7](#7-division-of-labour-decider-decides-bedrock-explains).

**Safety constraints followed while writing this:** no credentials were
requested, read, printed, or created. No AWS API call was made. No AWS CLI
command that mutates resources or incurs charges was run. The only AWS-related
commands suggested below are read-only (`sts get-caller-identity`,
`list-foundation-models`, `get-foundation-model-availability`) or are
documentation references the operator runs themselves.

All AWS facts below were read from official AWS documentation on **2026-10-23**.
Anything not confirmed there is in [§9 Unverified](#9-unverified--open-questions).

---

## 1. Supported SDK

### Recommended: `boto3` + the Converse API on `bedrock-runtime`

The canonical way to call a Bedrock model from a Python FastAPI app is `boto3`
against the `bedrock-runtime` endpoint, using the **Converse API**.

The Bedrock User Guide states:

> The Converse API is available on the `bedrock-runtime` endpoint only.
> …the Converse API provides a consistent API that works with all Amazon Bedrock
> models that support messages. This means you can write code once and use it
> with different models.

The official quick start shows exactly this shape:

```python
import boto3

client = boto3.client('bedrock-runtime', region_name='us-east-1')
response = client.converse(
    modelId='global.anthropic.claude-opus-5',
    messages=[
        {
            'role': 'user',
            'content': [{'text': 'Can you explain the features of Amazon Bedrock?'}]
        }
    ]
)
print(response)
```

Install requirement: `pip install boto3`.

**Why Converse rather than `invoke_model`:** `InvokeModel` is model-specific —
the request body is Anthropic's native Messages format, so the body shape
changes if you swap providers. Converse is provider-agnostic, supports
`system` blocks, `inferenceConfig`, and `toolConfig` in one shape, and is the
shape AWS documents for new applications.

### Alternatives considered

| Option | When it fits | Notes |
|---|---|---|
| **boto3 `converse`** | **Default choice for this project** | Provider-agnostic, one client, no extra dependencies beyond `boto3` |
| `boto3` `invoke_model` | You need Anthropic-native features (caching blocks, compaction) | Body is Anthropic-specific: `{"anthropic_version": "bedrock-2023-05-31", "messages": [...], "max_tokens": N}` |
| `boto3` `invoke_model_with_response_stream` | You want token streaming | Same request body as `invoke_model` |
| Anthropic-native Messages API (`pip install "anthropic[bedrock]" aws-bedrock-token-generator`) | You want the Anthropic SDK's ergonomics | Uses the `bedrock-mantle` endpoint. Note: `bedrock-mantle` does **not** support Converse or Invoke — only Messages |
| **Strands Agents `BedrockModel`** | You build the agent loop on Strands | Pairs naturally with Decider 2B. `strands-agents` 1.62.0 is Apache-2.0 and already pulls in `boto3` |

**Note on the `bedrock-mantle` endpoint.** AWS's quick start documents an API-key
flow that sets `ANTHROPIC_BASE_URL="https://bedrock-runtime.<region>.amazonaws.com/anthropic"`.
Per the Claude 5.5 model cards, that Messages API path is served by the
`bedrock-mantle` endpoint, which supports **Messages only** — not Converse, not
Invoke. For this project that matters: the Converse API must be called against
`bedrock-runtime`, which is a different client (`bedrock-runtime` vs
`bedrock-mantle`).

---

## 2. Model choice and model IDs

For a short, factual "explain these numbers" turn, a **Haiku**-class model is the
natural fit: the Bedrock model card describes Claude Haiku 5.5 as *"the fastest
and most efficient model in the Claude 5.5 family, built for high-volume,
latency-sensitive work"*, with a 1M-token context window and 128K max output
tokens.

### Verified model IDs (from the official model cards)

| Model | Base model ID | Geo inference IDs | Global inference ID |
|---|---|---|---|
| Claude Haiku 5.5 | `anthropic.claude-haiku-5-5` | `us.` / `eu.` / `au.` / `jp.anthropic.claude-haiku-5-5` | `global.anthropic.claude-haiku-5-5` |
| Claude Sonnet 5.5 | `anthropic.claude-sonnet-5-5` | `us.` / `eu.` / `au.anthropic.claude-sonnet-5-5` | `global.anthropic.claude-sonnet-5-5` |

Both support **Converse** and **Invoke** on `bedrock-runtime`, plus streaming,
guardrails, prompt caching, and structured outputs.

The ID you pass to `modelId` is the **inference profile** ID (`global.…`,
`us.…`, or the bare base ID for in-region inference), not the bare base ID.
AWS's own example: *"to use Global cross-Region inference from us-east-1
(N. Virginia), use the endpoint URL `https://bedrock-runtime.us-east-1.amazonaws.com`
with the inference profile ID `global.anthropic.claude-haiku-5-5`."*

### Marketplace product IDs (needed if you scope IAM by product)

| Model | Marketplace product ID |
|---|---|
| Claude Haiku 5.5 | `prod-6cyn7tgqazjhu` |
| Claude Sonnet 5.5 | `prod-pjfguoisodbd6` |

The `aws-marketplace:Subscribe` action can be scoped with the
`aws-marketplace:ProductId` condition key using these values.

---

## 3. Region and endpoint selection

### Bedrock inference regions (official list)

`us-east-1`, `us-east-2`, `us-west-2`, `af-south-1`, `ap-south-1`,
`ap-northeast-2`, `ap-southeast-1`, `ap-southeast-2`, `ap-northeast-1`,
`ca-central-1`, `eu-central-1`, `eu-west-1`, `eu-west-2`, `eu-west-3`,
`eu-north-1`, `sa-east-1`, `us-gov-west-1`.

### Cross-region inference profiles

AWS provides system-defined cross-region profiles with a geographic prefix:

| Geography | Regions in the profile |
|---|---|
| US (`us`) | `us-east-1`, `us-east-2`, `us-west-2` |
| Europe (`eu`) | `eu-central-1`, `eu-north-1`, `eu-west-1`, `eu-west-3` |
| Asia Pacific (`apac`) | `ap-northeast-1`, `ap-northeast-2`, `ap-south-1`, `ap-southeast-1`, `ap-southeast-2` |

### Important for an India-focused project

For **Claude Haiku 5.5 and Claude Sonnet 5.5**, the model card's regional
availability table shows `ap-south-1` (Mumbai) with:

- In-Region: **not supported**
- Geo: **not supported**
- Global: **supported**

So from `ap-south-1` the only working option for these models is the **Global**
inference profile, e.g. `modelId="global.anthropic.claude-haiku-5-5"` with
`region_name="ap-south-1"`. Using `us.anthropic.claude-haiku-5-5` from
`ap-south-1` would fail. AWS notes that *"cross-region profiles are not
available in every Region where Bedrock itself is available"*.

The `backend/.env` already carries an `AWS_REGION` placeholder, so the region is
a configuration decision, not a code change.

---

## 4. Authentication (profile / SSO)

### Credential provider chain

The AWS SDK for Python resolves credentials in this documented order:

1. Credentials passed explicitly to `boto3.Session(...)`
2. Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`)
3. The shared credentials file
4. The shared config file
5. **IAM Identity Center (formerly AWS SSO) credentials**
6. Container credentials
7. The IAM role attached to an EC2 instance

### Named profile

```python
import boto3

session = boto3.Session(profile_name="myprofile")
client = session.client("bedrock-runtime", region_name="ap-south-1")
```

> The argument is **`profile_name=`**, not `profile=`. `profile=` is the legacy
> `boto` (v2) API. If older documentation shows `profile=`, it is not `boto3`.

The same effect via environment variable:

```python
import os
os.environ["AWS_PROFILE"] = "myprofile"
session = boto3.Session()
```

An explicit `profile_name=` takes precedence over `AWS_PROFILE`.

### IAM Identity Center (SSO)

SSO profile definitions live in the shared **config** file
(`%USERPROFILE%\.aws\config` on Windows), and modern configuration separates the
SSO session from the account/role assignment:

```ini
[profile my-sso-profile]
sso_session = my-sso
sso_account_id = 123456789012
sso_role_name = SampleRole
region = ap-south-1

[sso-session my-sso]
sso_start_url = https://my-sso-portal.awsapps.com/start
sso_region = ap-south-1
sso_registration_scopes = sso:account:access
```

Then either `boto3.Session(profile_name="my-sso-profile")` or
`AWS_PROFILE=my-sso-profile`.

The SDK uses the **cached SSO login token** under
`%USERPROFILE%\.aws\sso\cache` (Windows). If there is no valid cached login,
SSO credential resolution fails and a new login is required:

```powershell
aws sso login --profile my-sso-profile
```

`aws sso login` performs a browser sign-in and writes only a local cache token —
it creates no AWS resource and incurs no charge.

### File locations (Windows)

| File | Path |
|---|---|
| Shared credentials | `%USERPROFILE%\.aws\credentials` |
| Shared config | `%USERPROFILE%\.aws\config` |
| SSO token cache | `%USERPROFILE%\.aws\sso\cache` |

### API keys (quick start only — not for this project)

The Bedrock quick start documents a short-term or long-term Bedrock API key used
as a bearer token:

```powershell
$env:AWS_BEARER_TOKEN_BEDROCK="<provide your Bedrock API key>"
```

This requires **boto3 1.39.0 or later**; earlier versions ignore the variable
and fail with `Unable to locate credentials`. AWS's own quick start states:
*"For production applications, use IAM roles or temporary credentials."*
**MarketQuest AI should use a profile / SSO, not an API key** — the project
README already states this preference, and `backend/.env` already has an
`AWS_PROFILE` placeholder.

### State of this machine (read-only checks, 2026-10-23)

| Check | Result |
|---|---|
| `aws` CLI on PATH | **Not installed** |
| `%USERPROFILE%\.aws\config` exists | **No** |
| `%USERPROFILE%\.aws\credentials` exists | **No** |

**Consequence:** there is currently no AWS profile, no SSO configuration, and no
CLI on this machine, so no live Bedrock call could be made even if one were
attempted. Nothing was read beyond the *existence* of those two paths; their
contents were never opened. This is a **setup gap, not a code gap** — see
[§8](#8-what-the-operator-must-do-first).

---

## 5. Required IAM permissions

### Actions the Converse API needs

From the AWS Service Authorization Reference for Amazon Bedrock, the relevant
actions are:

| Action | AWS description | Access |
|---|---|---|
| `bedrock:Converse` | "Grants permission to invoke a Bedrock model using the Converse API" | Write |
| `bedrock:ConverseStream` | "Grants permission to invoke a Bedrock model using the ConverseStream API" | Write |
| `bedrock:InvokeModel` | "Grants permission to invoke a Bedrock model" | Write |
| `bedrock:InvokeModelWithResponseStream` | "Grants permission to invoke a Bedrock model and receive a response stream" | Write |
| `bedrock:ListFoundationModels` | "Grants permission to list Bedrock foundation models" | List |
| `bedrock:GetFoundationModel` | "Grants permission to get details about a Bedrock foundation model" | Read |
| `bedrock:GetFoundationModelAvailability` | "Grants permission to get the availability of a Bedrock foundation model in a region" | Read |
| `bedrock:ListInferenceProfiles` | "Grants permission to list inference profiles" | List |
| `bedrock:ListRegionalInferenceProfiles` | "Grants permission to list regional inference profiles" | List |

> **One documentation wrinkle worth flagging.** The Bedrock User Guide's
> "Deny access for inference of foundation models" example says that when
> `bedrock:InvokeModel` is denied, *"Other actions, such as `Converse` and
> `StartAsyncInvoke`, are blocked automatically"*. That sentence is about how a
> **Deny** statement propagates, not about what an **Allow** must contain. The
> Service Authorization Reference lists `bedrock:Converse` as its own action,
> so an Allow policy that grants only `bedrock:InvokeModel` should not be
> assumed to permit Converse. Grant `bedrock:Converse` explicitly. (Marked
> unverified — see [§9](#9-unverified--open-questions) item 1.)

### AWS Marketplace permissions (one-time)

Access to serverless Bedrock models sold through AWS Marketplace is controlled
by:

- `aws-marketplace:Subscribe`
- `aws-marketplace:Unsubscribe`
- `aws-marketplace:ViewSubscriptions`

AWS notes these are *"only required the first time a model is being used in an
account"* — after the model is enabled for the account, users do not need
subscription permissions to invoke it.

### Anthropic first-time-use (FTU) requirement

> For Anthropic models, you must complete the First Time Use (FTU) form before
> invoking the model.

This is once per account (or once per organisation's management account). It is
*not* satisfied by the Marketplace subscription. Until it is submitted,
invocations return `AccessDeniedException`. The form can be submitted in the
console (Model catalog → Anthropic provider page) or via the
`PutUseCaseForModelAccess` API.

### Least-privilege policy for this project

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "MarketQuestConverse",
      "Effect": "Allow",
      "Action": [
        "bedrock:Converse"
      ],
      "Resource": [
        "arn:aws:bedrock:ap-south-1::foundation-model/anthropic.claude-haiku-5-5",
        "arn:aws:bedrock:ap-south-1:123456789012:inference-profile/global.anthropic.claude-haiku-5-5"
      ]
    },
    {
      "Sid": "MarketQuestModelDiscovery",
      "Effect": "Allow",
      "Action": [
        "bedrock:ListFoundationModels",
        "bedrock:GetFoundationModel",
        "bedrock:GetFoundationModelAvailability",
        "bedrock:ListInferenceProfiles",
        "bedrock:ListRegionalInferenceProfiles"
      ],
      "Resource": "*"
    }
  ]
}
```

Two structural notes on ARN formats, from the Service Authorization Reference:

```text
# Foundation model — NOTE the empty account field
arn:${Partition}:bedrock:${Region}::foundation-model/${ModelId}

# Inference profile
arn:${Partition}:bedrock:${Region}:${AccountId}:inference-profile/${InferenceProfileId}
```

For an AWS-created inference profile, use the exact `inferenceProfileArn`
returned by Bedrock rather than hand-assembling it.

---

## 6. Checking model access in the target region

### In the console

> **Most models** – Choose **Model catalog** in the navigation pane, choose a
> model, and then open it in the playground. Amazon Bedrock starts the
> subscription for you on the first invocation, so there is no access request to
> submit.

For Anthropic models, submit the first-time use case details in the same place
before the first invocation. The **Model access** page under *Bedrock
configurations* applies to **AWS GovCloud (US)**; in commercial Regions most
models are enabled on first use.

### Programmatically — `GetFoundationModelAvailability` (recommended)

```powershell
aws bedrock get-foundation-model-availability --model-id anthropic.claude-haiku-5-5
```

```python
bedrock_client = boto3.client("bedrock", region_name="ap-south-1")
availability = bedrock_client.get_foundation_model_availability(
    modelId="anthropic.claude-haiku-5-5"
)
```

Documented response shape:

```json
{
  "modelId": "anthropic.claude-sonnet-4-20250514-v1:0",
  "agreementAvailability": {
    "status": "AVAILABLE"
  },
  "authorizationStatus": "AUTHORIZED",
  "entitlementAvailability": "AVAILABLE",
  "regionAvailability": "AVAILABLE"
}
```

`agreementAvailability.status` is `AVAILABLE`, `PENDING`, `NOT_AVAILABLE`, or
`ERROR` (with `errorMessage` describing the problem). **`PENDING` means
invoking still returns `AccessDeniedException`** even though the form was
submitted successfully.

### Listing models and profiles

```powershell
aws bedrock list-foundation-models --by-provider ANTHROPIC
aws bedrock list-inference-profiles
```

```python
bedrock_client.list_foundation_models(byProvider="ANTHROPIC")
bedrock_client.list_inference_profiles()
```

`ListFoundationModels` filters are `byProvider`, `byCustomizationType`
(`FINE_TUNING | CONTINUED_PRE_TRAINING | DISTILLATION`), `byInferenceType`
(`ON_DEMAND | PROVISIONED`), and `byOutputModality`
(`TEXT | IMAGE | EMBEDDING`).

> **Note:** the current `ListFoundationModels` response syntax returns
> `modelSummaries` with `modelId`, `modelArn`, `providerName`,
> `inferenceTypesSupported`, `modelLifecycle`, `inputModalities`,
> `outputModalities` and `responseStreamingSupported` — there is **no plain
> `access` Boolean** in the documented response shape. Use
> `GetFoundationModelAvailability` for the access/availability verdict.

### Confirming who you are calling as (read-only, free)

```powershell
aws sts get-caller-identity
```

This returns the account, ARN and principal id. It does not expose the secret
key, does not create a resource, and does not incur a charge. Note it *does*
print an account id, so treat the output as sensitive for a public demo
recording.

---

## 7. Division of labour: Decider decides, Bedrock explains

This is the crux of the hackathon requirement (*"an agent that uses Strands
Decider 2B for at least one meaningful decision, paired with Amazon Bedrock"*).

### What each component owns

| Component | Input | Output | Never does |
|---|---|---|---|
| **Strands Decider 2B** | The user question + the list of candidate tools | Exactly one tool id (or `no_action`) | Generates prose, calls tools, invents prices |
| **The FastAPI backend** | The tool id from Decider | Executes the matching `/market/*` service function and returns real computed numbers | Chooses the tool |
| **Amazon Bedrock (generative)** | The **already-computed** analysis payload | A written explanation of those numbers | Selects tools, computes statistics, invents prices |

### Why the split matters

- Decider 2B **does not generate text**. It scores typed options. Asking it to
  write an explanation is the wrong tool for the job and would fail.
- Bedrock **must not** be asked to pick the tool. Routing decisions are cheap
  and structured; that is exactly what the Decider is for. Letting a large
  generative model route is what the hackathon's *"Effective use of Decider 2B"*
  criterion is measuring against.
- The Bedrock call happens **after** the numbers exist. The prompt must carry
  the computed values, and the model must be told not to recompute or extend
  them.

### The prompt shape

Send the analysis as a **system** block establishing the role and the hard
constraints, and the payload as the **user** message.

```python
import json

system_prompt = (
    "You are the analyst for MarketQuest AI, a simulation game for Indian "
    "stocks. You explain market-analysis results that have already been "
    "computed by the backend.\n"
    "Rules:\n"
    "- Use ONLY the numbers in the supplied data. Never recompute, estimate, "
    "or add figures that are not present.\n"
    "- The prices are SYNTHETIC demo data, not real market data. Say so.\n"
    "- This is a simulation for learning. Never give investment advice, never "
    "recommend buying or selling, and never predict prices.\n"
    "- If a metric is missing, say it is unavailable rather than guessing.\n"
    "- Keep it under 150 words and plain-language."
)

user_content = {
    "symbol": analysis["symbol"],
    "observations": analysis["observations"],
    "period": {"first_date": analysis["first_date"], "last_date": analysis["last_date"]},
    "latest_close": analysis["latest_close"],
    "sma": analysis["sma"],
    "sma_window": analysis["sma_window"],
    "volatility": analysis["volatility"],
    "total_return_pct": analysis["total_return_pct"],
    "average_volume": analysis["average_volume"],
    "data_source": analysis["data_source"],
}

response = client.converse(
    modelId=model_id,
    system=[{"text": system_prompt}],
    messages=[{"role": "user", "content": [{"text": json.dumps(user_content, indent=2)}]}],
    inferenceConfig={"maxTokens": 600, "temperature": 0.2},
)
```

Design notes:

- `temperature` low (0.2) — this is a factual summarisation task, not creative
  writing.
- `maxTokens` bounded — explanations are short; this also bounds cost.
- The payload is sent as **JSON in a text block**, not as free prose, so the
  model is quoting values rather than re-deriving them.
- The `data_source` field is included so the model can honour the synthetic-data
  instruction with the real value in hand.

### Minimal safe request/response example

```python
"""Minimal Bedrock Converse call. Reads credentials from the ambient profile/SSO
chain. Never prints credentials. Does not create resources."""
import json
import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError

REGION = os.environ.get("AWS_REGION", "ap-south-1")
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "global.anthropic.claude-haiku-5-5")

profile = os.environ.get("AWS_PROFILE")  # None -> default chain
session = boto3.Session(profile_name=profile) if profile else boto3.Session()
client = session.client("bedrock-runtime", region_name=REGION)


def explain(analysis: dict) -> str:
    """Turn an already-computed analysis payload into a short explanation."""
    try:
        response = client.converse(
            modelId=MODEL_ID,
            system=[{"text": "You explain computed market-analysis results. "
                             "Use only the supplied numbers. This is synthetic "
                             "demo data. Never give investment advice."}],
            messages=[{
                "role": "user",
                "content": [{"text": json.dumps(analysis, indent=2)}],
            }],
            inferenceConfig={"maxTokens": 600, "temperature": 0.2},
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "Unknown")
        if code == "AccessDeniedException":
            raise RuntimeError(
                "Bedrock denied the call. Check IAM (bedrock:Converse), the "
                "Anthropic first-time-use form, and model access in this region."
            ) from exc
        raise
    except BotoCoreError as exc:
        raise RuntimeError("Could not reach Bedrock.") from exc

    # The response body is a list of content blocks; take the first text block.
    blocks = response["output"]["message"]["content"]
    text = next((b["text"] for b in blocks if "text" in b), "")

    # Usage and stop reason are useful for logging and cost tracking.
    usage = response.get("usage", {})
    print(
        f"stopReason={response.get('stopReason')} "
        f"inputTokens={usage.get('inputTokens')} "
        f"outputTokens={usage.get('outputTokens')}"
    )
    return text
```

Response shape, per the Converse API reference: the generated text is at
`response["output"]["message"]["content"][0]["text"]`; `response["stopReason"]`
reports why generation stopped; `response["usage"]` carries `inputTokens`,
`outputTokens` and `totalTokens`.

**Safety properties of this example**

- It never reads, prints, or logs a credential. `boto3` resolves them from the
  ambient chain; the code only names a *profile*, never a key.
- It performs no resource-creating call.
- It fails loudly with an actionable message on `AccessDeniedException` rather
  than silently returning a generic message.
- It returns a plain string, so the caller can put it behind the same
  error handling as the rest of the API.

### What must never happen

- Never call Bedrock with the *tool list* and ask it to pick a tool — that is
  the Decider's job, and doing it in Bedrock undermines the hackathon's
  *"Effective use of Decider 2B"* criterion.
- Never let the model produce the numbers. It receives them.
- Never let the model emit a buy/sell recommendation, a price target, or a
  prediction. The system prompt above constrains this; a demo video showing
  "DEMOTECH looks like a buy" would be a correctness and safety problem, not a
  feature.

---

## 8. What the operator must do first

Nothing here was done during this research, and none of it should be done by an
automated agent. All steps are the account owner's.

1. **Install the AWS CLI v2** (not present on this machine).
2. **Configure a profile or SSO.** Either add a `[profile ...]` section to
   `%USERPROFILE%\.aws\config`, or configure IAM Identity Center and run
   `aws sso login --profile <name>`.
3. **Choose a region.** For an India-focused project, `ap-south-1` is natural —
   but note from [§3](#3-region-and-endpoint-selection) that Claude 5.5 models
   there support **Global** inference only, so the `modelId` must be
   `global.anthropic.claude-haiku-5-5`, not `us.…`.
4. **Grant IAM permissions** ([§5](#5-required-iam-permissions)) to the profile's
   role, including `bedrock:Converse` and the read-only discovery actions.
5. **Submit the Anthropic first-time-use form** (once per account).
6. **Verify access** with `get-foundation-model-availability` before writing
   code, so a missing permission is not mistaken for a code bug.
7. **Set `AWS_REGION`, `AWS_PROFILE` and `BEDROCK_MODEL_ID`** in `backend/.env`.
   Those placeholders already exist. `AWS_PROFILE` in the *backend* env file is
   fine; never put AWS secrets in `frontend/.env`, because Vite bundles frontend
   env vars into browser code.

---

## 9. Unverified / open questions

1. **Whether `bedrock:InvokeModel` alone grants Converse.** The Service
   Authorization Reference lists `bedrock:Converse` as a separate action, the
   Converse API reference states *"This operation requires permission for the
   `bedrock:InvokeModel` action"*, and the User Guide's Deny-policy example
   says denying `InvokeModel` also blocks `Converse`. The docs therefore name
   **both** actions, and the Allow-side requirement was **not** confirmed
   experimentally. Recommendation: grant `bedrock:Converse` **and**
   `bedrock:InvokeModel` on the model and the inference profile. Unverified —
   a single `Converse` call after the account setup will name whichever
   action is missing.
2. **This account's Bedrock status.** Whether the target account has Bedrock
   enabled, which models it has access to, and whether the Anthropic FTU form
   has been submitted — **all unknown**, because no AWS call was made and no
   credentials exist on this machine.
3. **Exact per-token pricing** for the chosen model. Not looked up; the model
   cards point to the Bedrock pricing page. Unverified.
4. **`ap-south-1` model coverage for models other than Claude 5.5.** Only the
   two Claude 5.5 cards were read in detail. Unverified for other providers.
5. **Strands Agents `BedrockModel` specifics.** The Strands model-provider page
   returned HTTP 404 when fetched, so the exact import path and constructor
   arguments for `BedrockModel` are **not** documented here. Unverified — check
   `strandsagents.com` directly before relying on it.
6. **Whether `bedrock:Converse` has a separate regional availability gate.**
   Not confirmed. Unverified.
7. **Streaming vs non-streaming choice.** The example uses non-streaming
   `converse` for simplicity. Whether the demo should stream (`converse_stream`)
   depends on the UI, and is not decided here.

---

## 10. What was implemented

**The integration is built and covered by mocked tests. No live AWS call has
been made.** The code follows this document, and the Converse request and
response shapes were re-read against the AWS API reference on 2026-10-23
before the code was written.

### The files

| File | What it does |
|---|---|
| `backend/app/services/bedrock.py` | The Bedrock client. Builds the Converse request, parses the response, and maps every AWS failure onto a typed error. `boto3` is imported lazily, so the backend still starts without it. |
| `backend/app/agent/explainer.py` | Builds the bounded payload and the prompt, calls the client, and maps its errors onto the two statuses the API reports. |
| `backend/app/api/agent.py` | `POST /agent/decide` now asks for an explanation after the tool has run, and reports what happened. `GET /agent/status` reports Bedrock readiness. |
| `backend/app/core/config.py` | `AWS_REGION`, `AWS_PROFILE`, `BEDROCK_MODEL_ID`, `BEDROCK_TIMEOUT_SECONDS`, `BEDROCK_MAX_TOKENS`, `BEDROCK_TEMPERATURE`, `BEDROCK_ENABLED`. |
| `backend/tests/test_bedrock.py` | 38 mocked tests. `backend/tests/conftest.py` installs a fake `bedrock-runtime` client for the **whole suite**, so no test can reach AWS. |

`boto3==1.43.118` is the one new dependency. Nothing else was added, and no
existing dependency was upgraded.

### The contract, in code

The division of labour in [§7](#7-division-of-labour-decider-decides-bedrock-explains)
is enforced by the shape of the code, not by convention:

- `app/agent/tools.py` is the allowlist. Only the Decider's choice reaches it,
  and only the name is looked up.
- The tool runs through `app/services/market_queries.py`, the same builders the
  `/market` endpoints use. Bedrock is not in that path.
- `app/agent/explainer.py` receives the **already-computed** response model. It
  cannot reach a tool registry, and it is never given a list of tools to pick
  from.

### What the model is given

The prompt is a `system` block (the role and the hard constraints) plus a
`user` block carrying the computed result as JSON. Two details are worth
stating, because they are what stop the model from getting a number wrong:

1. **The units are pre-converted.** Volatility and the daily returns are
   stored as decimal fractions, and `total_return_pct` is already a
   percentage. The payload converts the fractions to percentages **once, in
   the backend**, and names every such field `*_pct`. The model quotes a
   number; it never converts one. This is the one place the backend does
   arithmetic, and it is a unit conversion, not a new statistic.
2. **The series is bounded.** The backend holds all 30 daily rows, but only
   the first 8 and the last 8 are sent, and the payload says so: *"Showing the
   first 8 and last 8 of 30 rows. The rows in between were not provided, so do
   not describe them."* The model cannot describe a row it was not given.

The system prompt also states that the data is synthetic, forbids investment
advice and predictions, and says to call a missing figure unavailable rather
than guess.

### What the API returns

`POST /agent/decide` gains three fields and one object. The existing fields,
including the Decider's probabilities and confidence, are unchanged.

| Field | Meaning |
|---|---|
| `explanation` | The Bedrock text. Present **only** when the status is `generated`. |
| `explanation_status` | `generated`, `skipped`, `disabled`, `unavailable` or `failed`. |
| `explanation_error` | Why there is no explanation, when the status is not `generated`. |
| `bedrock` | The model id, region, stop reason and token counts. Present only on success. |

### When Bedrock cannot do its job

**A Bedrock failure never fails the request and never produces a fabricated
explanation.** The decision and the market data are real whatever the
explanation layer does, so the request still succeeds and the failure is
reported in its own field.

| Status | Cause | HTTP status |
|---|---|---|
| `generated` | The call succeeded. | `200` |
| `skipped` | The caller passed `"explain": false`, or the Decider chose `no_action` and there is nothing to explain. **No call is made**, so nothing is charged. | `200` |
| `disabled` | `BEDROCK_ENABLED=false`. | `200` |
| `unavailable` | Bedrock could not be used at all: `boto3` is missing, no credentials resolved, the profile was not found, the model is unknown in this region, or access was denied. **No request succeeded.** | `200` |
| `failed` | A request was made and did not produce a usable explanation: throttled, timed out, the service was unavailable, or the response was not in the documented shape. | `200` |

The error messages are written by hand rather than taken from the AWS
exception, so whatever the SDK put in the message — request ids, internal
detail — is never echoed to the caller. There is a test that asserts this.

### What was tested, and what was not

**Tested with mocks.** 38 new tests, 105 in total, all passing. The AWS
boundary is a fake `bedrock-runtime` client; the *real* `BedrockClient` sits
in front of it, so the request building, the response parsing and the error
mapping all run for real. The tests cover: the exact Converse request shape;
a successful response and its usage figures; seven malformed responses; and
missing credentials, access denied, an unknown model, throttling, a read
timeout, a connect timeout, an unreachable endpoint, and an unrecognised
error. On the endpoint side they cover: the explanation being returned, the
Decider's metadata being preserved, `unavailable` and `failed` producing no
text at all, `explain: false` and `no_action` making **no** call at all, and
all four tool kinds being explainable.

**Not tested with a live call.** No AWS request has been made, because no
credential exists on this machine and the brief requires approval before a
billable call. The parts that a live call would exercise, and that the mocks
cannot cover, are: whether the account's IAM policy allows `Converse`, whether
the Anthropic first-time-use form has been submitted, whether the model is
enabled in `ap-south-1`, and the real latency and token cost.

### Outstanding AWS-side actions

Still the account owner's, exactly as in [§8](#8-what-the-operator-must-do-first).
The code is ready for them: once a profile resolves and the model is enabled,
`POST /agent/decide` starts returning an explanation with no further change.

---

## 11. Sources

All read from official AWS documentation on 2026-10-23. The Converse API
reference and the Claude Haiku 5.5 model card were **re-read on 2026-10-23**
before the implementation, to confirm the request shape, the response shape,
the model ids and the `ap-south-1` availability that this document relies on.

- Bedrock quick start (client creation, Converse example) — https://docs.aws.amazon.com/bedrock/latest/userguide/getting-started.html
- Converse API reference (request syntax, response syntax, error codes) — https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html
- Inference using the Converse API — https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.md
- Models at a glance — https://docs.aws.amazon.com/bedrock/latest/userguide/model-cards.html
- Anthropic model cards — https://docs.aws.amazon.com/bedrock/latest/userguide/model-cards-anthropic.md
- Claude Haiku 5.5 model card (model IDs, regional availability, sample code) — https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-5-5.md
- Claude Sonnet 5.5 model card — https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5-5.md
- Request access to models (Marketplace permissions, Anthropic FTU, availability API) — https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html
- Identity-based policy examples — https://docs.aws.amazon.com/bedrock/latest/userguide/security_iam_id-based-policy-examples.html
- Service Authorization Reference for Amazon Bedrock (IAM actions, ARN formats) — https://docs.aws.amazon.com/service-authorization/latest/reference/list_amazonbedrock.html
- ListFoundationModels API reference — https://docs.aws.amazon.com/bedrock/latest/APIReference/API_ListFoundationModels.html
- Bedrock regions and cross-region inference profiles — https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-regions.html
- AWS SDK for Python credential configuration (chain, `profile_name`, SSO) — https://docs.aws.amazon.com/sdk-for-python/latest/v3/developer-guide/configuring-credentials.html
